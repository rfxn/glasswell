#!/usr/bin/env bash
# The deploy runbook (infra/README.md steps 1, 2 and 4) as a script rather than as prose.
# Read-write on the host and read-only here. Two refusals are the point of it: a dirty tree
# deploys bytes that are in no commit, and an untagged HEAD deploys a release nobody can name.
set -uo pipefail

REPO_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
HOST="${GW_DEPLOY_HOST:-root@192.168.2.111}"
DEPLOY_SRC=/opt/glasswell/src
WEB_ROOT=/opt/glasswell/web
VENV=/opt/glasswell/venv
LOCK=requirements.lock

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
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run) dry_run=1; shift ;;
        --with-migrations) with_migrations=1; shift ;;
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

tag="$(git describe --exact-match --tags HEAD 2>/dev/null)"  # no tag here is the signal, not an error
if [[ -z $tag ]]; then
    if [[ ${GW_DEPLOY_ALLOW_UNTAGGED:-0} != 1 ]]; then
        refuse "HEAD carries no tag — cut one with \`make release\`, or set GW_DEPLOY_ALLOW_UNTAGGED=1"
    fi
    tag="(untagged $(git rev-parse --short HEAD))"
fi

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
printf 'deploying %s (%s)\n' "$tag" "$(git rev-parse --short HEAD)"

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
    printf '  %s unchanged — nothing to install\n' "$LOCK"
else
    remote "$VENV/bin/pip install -q -r $DEPLOY_SRC/$LOCK && \
            $VENV/bin/pip install -q -e $DEPLOY_SRC --no-deps" || refuse "dependency install failed"
fi

step "5. config and units (idempotent)"
remote "cd $DEPLOY_SRC/infra && ./install.sh" || refuse "install.sh failed"

if (( with_migrations )); then
    step "6. migrations, as the postgres superuser"
    remote "sudo -u postgres $VENV/bin/glasswell-migrate \
            --dsn 'postgresql:///glasswell?host=/var/run/postgresql'" || refuse "migrations failed"
else
    printf '\n   (migrations skipped — pass --with-migrations, or runbook step 3 by hand)\n'
fi

# Both, as runbook step 4 has it. martin reads its source catalogue at startup and install.sh
# above can have just placed infra/martin/config.yaml, so without this the new config is inert
# and verify.sh's catalogue check fails the deploy two steps later.
step "7. restart"
remote "systemctl restart glasswell-api" || refuse "glasswell-api did not restart"
remote "systemctl restart martin" || refuse "martin did not restart"

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
