#!/usr/bin/env bash
# The deploy runbook (infra/README.md steps 1, 2 and 4) as a script rather than as prose.
# Read-write on the host and read-only here. The refusals are the point of it: a dirty tree
# deploys bytes that are in no commit, an untagged HEAD deploys a release nobody can name,
# and a migration gap deploys code its schema cannot carry.
set -uo pipefail

REPO_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
HOST="${GW_DEPLOY_HOST:-root@192.168.2.111}"
DEPLOY_SRC=/opt/glasswell/src
WEB_ROOT=/opt/glasswell/web
VENV=/opt/glasswell/venv
LOCK=requirements.lock
SOCKET_DSN='postgresql:///glasswell?host=/var/run/postgresql'
# The role every ingest and mart refresh runs as, and therefore the one that must own anything
# those refreshes replace.
PIPELINE_ROLE=glasswell
MIGRATIONS_DIR=src/glasswell/db/migrations
CODE_ENV_FILE=/etc/glasswell/code-version.env

dry_run=0
with_migrations=0

usage() {
    cat <<'EOF'
usage: deploy.sh [--dry-run] [--with-migrations]

  --dry-run           run the refusals, print every remote command, change nothing
  --with-migrations   also run runbook step 3 (migrations, as the postgres superuser)
  $GW_DEPLOY_HOST            ssh destination (default root@192.168.2.111, VM 111)
  $GW_DEPLOY_ALLOW_UNTAGGED  1 deploys a HEAD that carries no tag; rolling releases deploy tags

Runbook step 4's tile-function reinstall is deliberately not scripted: it is needed only when
src/glasswell/marts/tiles.py moved, and infra/README.md carries the command.

Runbook step 3b, the mart refresh after a migration that touched a tile mart, is not scripted
either. Its canonical form runs as postgres — the tile views are postgres-owned, and uid
glasswell gets InsufficientPrivilege — and carries the code identity this deploy stamped:
  systemd-run --uid=postgres --pipe --wait \
      --setenv=GLASSWELL_CODE_VERSION=<tag>+<short-commit> \
      /opt/glasswell/venv/bin/python -m glasswell.marts.nd_wells \
      --dsn 'postgresql:///glasswell?host=/var/run/postgresql'
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run) dry_run=1; shift ;;
        --with-migrations) with_migrations=1; shift ;;
        --skip-migrations)
            printf '%s\n' '--skip-migrations was retired: code and scheduled jobs must not outrun the schema' >&2
            exit 2
            ;;
        -h|--help) usage; exit 0 ;;
        *) printf 'unknown argument: %s\n' "$1" >&2; exit 2 ;;
    esac
done

refuse() { printf 'deploy refused: %s\n' "$1" >&2; exit 1; }
step() { printf '\n== %s\n' "$1"; }

cd "$REPO_DIR" || refuse "cannot enter $REPO_DIR"

dirty="$(git status --porcelain)"
if [[ -n $dirty ]]; then
    printf '%s\n' "$dirty" >&2
    refuse "the working tree is not clean — a deploy ships a commit, not a desk"
fi

short_commit="$(git rev-parse --short HEAD)"
tag="$(git describe --exact-match --tags HEAD 2>/dev/null)"  # no tag here is the signal, not an error
if [[ -z $tag ]]; then
    if [[ ${GW_DEPLOY_ALLOW_UNTAGGED:-0} != 1 ]]; then
        refuse "HEAD carries no tag — cut one with \`make release\`, or set GW_DEPLOY_ALLOW_UNTAGGED=1"
    fi
    code_version="untagged+$short_commit"
    tag="(untagged $short_commit)"
else
    code_version="$tag+$short_commit"
fi

repo_head=0
for migration_file in "$MIGRATIONS_DIR"/[0-9][0-9][0-9]_*.sql; do
    [[ -e $migration_file ]] || continue
    version="${migration_file##*/}"
    version="${version%%_*}"
    if (( 10#$version > repo_head )); then repo_head=$((10#$version)); fi
done
(( repo_head > 0 )) || refuse "no migrations under $MIGRATIONS_DIR — this is not a glasswell tree"

[[ -d tests ]] || refuse "tests/ is missing — smoke.sh reads its openapi snapshot on the host"
[[ -f web/dist/index.html ]] || refuse "web/dist is not built — run \`npm --prefix web run build\`"
[[ -f web/dist/changelog/index.html ]] || refuse \
    "web/dist/changelog/index.html is missing — the header stamp links to it; rebuild the bundle"

# The stamp's version and the changelog page are baked at build time, so a bundle older than
# either would deploy the previous release's page under this release's tag. `make ship`
# rebuilds after cutting; this refuses when someone skips that.
for baked in VERSION CHANGELOG.md; do
    [[ -f $baked ]] || continue
    if [[ $baked -nt web/dist/changelog/index.html ]]; then
        refuse "web/dist predates $baked — rebuild, or the tag ships the previous page"
    fi
done

printf 'host      %s\n' "$HOST"
printf 'deploying %s (%s)\n' "$tag" "$short_commit"

remote() {
    if (( dry_run )); then
        printf '  [dry-run] ssh %s -- %s\n' "$HOST" "$1" >&2
        return 0
    fi
    # The string was composed from this script's own constants; expanding it here is the intent.
    # shellcheck disable=SC2029
    ssh "$HOST" "$1"
}

pipe_remote() {
    # $1 is the remote command; stdin is the tar stream. Kept separate from `remote` so the
    # dry run can report the pipe without building the archive it would have sent.
    if (( dry_run )); then
        printf '  [dry-run] <tar> | ssh %s -- %s\n' "$HOST" "$1" >&2
        cat >/dev/null  # drain the producer so it does not die on SIGPIPE mid-report
        return 0
    fi
    # Same as `remote`: the constants are this script's, and the remote shell sees the result.
    # shellcheck disable=SC2029
    ssh "$HOST" "$1"
}

step "0. what the host is running now"
lock_before="$(remote "sha256sum $DEPLOY_SRC/$LOCK 2>/dev/null | cut -d' ' -f1")"  # absent on a first deploy, and empty is the right answer
lock_here="$(sha256sum "$LOCK" | cut -d' ' -f1)"
printf '  %s here / %s there\n' "${lock_here:0:12}" "${lock_before:0:12}"

# tar over ssh, never `rsync --delete`: it stalls on this path (infra/README.md step 1).
step "1. the tree at HEAD"
remote "mkdir -p $DEPLOY_SRC $WEB_ROOT" || refuse "cannot prepare $DEPLOY_SRC on $HOST"
git archive HEAD | pipe_remote "tar -x -C $DEPLOY_SRC" || refuse "the tree did not unpack"

# .gitattributes export-ignores tests/, and `git archive` honours that — but scripts/smoke.sh
# reads tests/contract/openapi_snapshot.json on the host, so the suite ships from the working
# tree instead. It is the same commit: the tree was asserted clean above.
step "2. tests/ from the working tree (export-ignored, and smoke.sh reads it)"
tar --exclude=node_modules --exclude=__pycache__ --exclude=.pytest_cache -cf - tests \
    | pipe_remote "tar -x -C $DEPLOY_SRC" || refuse "tests/ did not unpack"

step "3. the built frontend, changelog page included"
tar -C web/dist -cf - . | pipe_remote "tar -x -C $WEB_ROOT" || refuse "web/dist did not unpack"

step "4. python dependencies"
if [[ $lock_here == "$lock_before" ]]; then
    printf '  %s unchanged — dependency install skipped\n' "$LOCK"
else
    remote "$VENV/bin/pip install -q -r $DEPLOY_SRC/$LOCK" || refuse "dependency install failed"
fi
remote "$VENV/bin/pip install -q -e $DEPLOY_SRC --no-deps" \
    || refuse "project install failed — console entry points may be stale"

step "5. config and units (idempotent)"
remote "cd $DEPLOY_SRC/infra && ./install.sh" || refuse "install.sh failed"

# install.sh places this only under --with-martin-config, which a routine deploy never
# passes — so the live file drifted until verify.sh's equality check caught it (v0.21 saga).
step "5b. martin tile config from the tree"
remote "install -D -o root -g root -m 0644 $DEPLOY_SRC/infra/martin/config.yaml /etc/martin/config.yaml" \
    || refuse "could not install /etc/martin/config.yaml"
printf '  tree copy installed — the martin restart below adopts it\n'

# Lineage stamps code_version from this; without it derive() falls back to pkg:0.1.0 and
# code-addressed ids collide across releases (v0.30 saga's DeterminismViolation). Both units
# source this file after app.env, so the deploy stamp survives owner edits there.
step "5c. code identity for lineage"
remote "printf 'GLASSWELL_CODE_VERSION=%s\nGLASSWELL_LOCKFILE_SHA256=%s\n' '$code_version' '$lock_here' > $CODE_ENV_FILE && chmod 0644 $CODE_ENV_FILE" \
    || refuse "could not stamp $CODE_ENV_FILE"
printf '  GLASSWELL_CODE_VERSION=%s\n' "$code_version"
printf '  GLASSWELL_LOCKFILE_SHA256=%s...\n' "${lock_here:0:12}"

code_env="GLASSWELL_CODE_VERSION=$code_version GLASSWELL_LOCKFILE_SHA256=$lock_here"
head_query="sudo -u postgres psql -d glasswell -tAc \"select case when to_regclass('public.schema_migrations') is null then 0 else (select coalesce(max(version), 0) from public.schema_migrations) end\""
integer_re='^[0-9]+$'

if (( with_migrations )); then
    step "6. migrations, as the postgres superuser"
    remote "sudo -u postgres env $code_env $VENV/bin/glasswell-migrate \
            --dsn '$SOCKET_DSN'" || refuse "migrations failed"
else
    step "6. migration head, repo vs database"
    if (( dry_run )); then
        remote "$head_query"
        printf '  [dry-run] repo head is %03d; the live comparison needs a database\n' "$repo_head"
    else
        db_head="$(remote "$head_query")" || refuse "cannot read the schema_migrations head"
        db_head="${db_head//[[:space:]]/}"
        [[ $db_head =~ $integer_re ]] || refuse "schema_migrations head answered '$db_head', not a number"
        if (( repo_head > db_head )); then
            refuse "the repo carries migrations ahead of the database (repo head $repo_head, database $db_head) — pass --with-migrations to apply them"
        fi
        printf '  schema is current at head %03d\n' "$db_head"
    fi
fi

# Idempotent by contract (seed_all's docstring), so every deploy runs it: a release whose new
# conformance rules never reach the registry FK-fails its first ingest (v0.21 saga, item 2).
step "6b. seed registries, as postgres"
remote "sudo -u postgres env $code_env $VENV/bin/python -c 'import psycopg; from glasswell.seed import seed_all; connection = psycopg.connect(\"$SOCKET_DSN\"); print(\"   \", seed_all(connection)); connection.commit(); connection.close()'" \
    || refuse "seed_all failed"

# martin refuses to start if any configured source is unresolvable, so one layer whose mart has
# never been refreshed takes every tile down with it -- which is how v0.69 lost nd_wells and
# tx_wells to three empty New Mexico and boundary layers. The functions are create-or-replace and
# read their own source relation, so installing them all here decouples "the layer exists" from
# "its mart has been populated": an empty layer answers 204 instead of refusing to boot.
step "6b2. tile functions for every configured layer"
remote "sudo -u postgres env $code_env $VENV/bin/python -c 'import psycopg; from glasswell.marts.tiles import install_tile_functions; connection = psycopg.connect(\"$SOCKET_DSN\"); print(\"   \", len(install_tile_functions(connection)), \"tile functions\"); connection.commit(); connection.close()'" \
    || refuse "tile function install failed"
# Installed as superuser so it can replace any of them, then handed to the pipeline role: every
# mart refresh calls install_tile_functions itself, and CREATE OR REPLACE requires ownership. A
# function first created here would otherwise be owned by postgres and refuse the next refresh,
# which is how a marts refresh died on `must be owner of function nd_survey_traces`.
step "6b3. tile functions owned by the pipeline role"
remote "sudo -u postgres psql -d glasswell -tAc \"select format('alter function %s owner to $PIPELINE_ROLE;', p.oid::regprocedure) from pg_proc p join pg_namespace n on n.oid = p.pronamespace join pg_roles r on r.oid = p.proowner where n.nspname = 'marts' and r.rolname <> '$PIPELINE_ROLE'\" | sudo -u postgres psql -d glasswell -q" \
    || refuse "could not hand the tile functions to $PIPELINE_ROLE"

step "6c. current ND physical-neighbour mart"
remote "sudo -u glasswell env $code_env $VENV/bin/glasswell-neighbors --dsn '$SOCKET_DSN'" \
    || refuse "ND physical-neighbour refresh failed"

# Both are idempotent — the mart refresh is delete-then-insert under a content-addressed
# derivation, the design promotion is `on conflict do nothing` — so a re-deploy is a no-op
# rather than a duplication. They run before verify because verify asserts on their output.
step "6d. per-well cumulative marts"
remote "sudo -u glasswell env $code_env $VENV/bin/python -m glasswell.marts.cumulatives --dsn '$SOCKET_DSN'" \
    || refuse "cumulatives refresh failed"

# Exits 0 with a stated outcome on a host that has never fetched the 440 MB archive: nothing
# to promote is a plan, not a failure.
step "6e. FracFocus completion-design backfill"
remote "sudo -u glasswell env $code_env $VENV/bin/glasswell-fracfocus --promote-design --dsn '$SOCKET_DSN'" \
    || refuse "completion-design backfill failed"

# Both, as runbook step 4 has it. martin reads its source catalogue at startup and install.sh
# above can have just placed infra/martin/config.yaml, so without this the new config is inert
# and verify.sh's catalogue check fails the deploy two steps later.
step "7. restart"
remote "systemctl restart glasswell-api" || refuse "glasswell-api did not restart"
remote "systemctl restart martin" || refuse "martin did not restart"

# uvicorn re-binds its unix socket after restart; verify.sh probes it immediately and a
# not-yet-bound socket reads as six 000s (seen live on the v0.20 deploy). Wait for readiness.
step "7b. wait for the api socket"
ready=""
for (( attempt = 0; attempt < 30; attempt++ )); do
    if remote "curl -sf -o /dev/null --unix-socket /run/glasswell/api.sock --max-time 2 http://localhost/healthz"; then
        ready=1
        break
    fi
    sleep 1
done
[[ -n "$ready" ]] || refuse "the api did not answer /healthz within 30s of restart"

# The timer is the ongoing guarantee, but deployment needs a snapshot from this exact code and
# the just-restarted dependencies before verify exercises the keyed status route.
step "7c. fresh status snapshot"
remote "systemctl start glasswell-status.timer" \
    || refuse "glasswell-status timer did not start"
remote "systemctl start glasswell-lineage-retention.timer" \
    || refuse "glasswell-lineage-retention timer did not start"
# The timer only, never the service: its ExecStart fetches from Cloudflare with a 30 s curl
# budget, and a deploy step must not wait on someone else's network.
remote "systemctl start glasswell-cf-ranges.timer" \
    || refuse "glasswell-cf-ranges timer did not start"
remote "systemctl start glasswell-lineage-retention.service" \
    || refuse "glasswell-lineage-retention did not complete"
if remote "systemctl is-enabled --quiet glasswell-restore-drill.timer"; then
    remote "systemctl start glasswell-restore-drill.timer" \
        || refuse "enabled restore-drill timer did not start"
fi
remote "systemctl start glasswell-status.service" \
    || refuse "glasswell-status did not produce a fresh snapshot"

# martin reads its entire source catalogue from PostgreSQL at startup, so /health answers
# before /catalog is populated — and verify.sh's per-layer assertions read the catalogue.
# Without this the gate fails a deploy that was fine (F11).
step "7d. wait for the martin catalogue"
ready=""
for (( attempt = 0; attempt < 30; attempt++ )); do
    if remote "curl -sf --max-time 2 http://127.0.0.1:3000/catalog | python3 -c 'import json,sys; sys.exit(0 if json.load(sys.stdin).get(\"tiles\") else 1)'"; then
        ready=1
        break
    fi
    sleep 1
done
[[ -n "$ready" ]] || refuse "martin did not publish a catalogue within 30s of restart"

step "8. verify.sh"
remote "$DEPLOY_SRC/infra/verify.sh"
verify_status=$?

step "9. smoke.sh"
remote "$DEPLOY_SRC/scripts/smoke.sh"
smoke_status=$?

printf '\n== result\n'
printf '  deployed  %s to %s\n' "$tag" "$HOST"
printf '  verify.sh exit %d\n' "$verify_status"
printf '  smoke.sh  exit %d\n' "$smoke_status"
(( verify_status == 0 && smoke_status == 0 )) || exit 1
