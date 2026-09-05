#!/usr/bin/env bash
# Place the glasswell host configuration. Idempotent: safe to re-run after every deploy.
set -euo pipefail

INFRA_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ETC_DIR=/etc/glasswell
STATE_DIR=/var/lib/glasswell
RUNS_DIR="$STATE_DIR/runs"
RUN_LOG_DIR=/var/log/glasswell
UNIT_DIR=/etc/systemd/system
SBIN_DIR=/usr/local/sbin
WEB_ROOT=/opt/glasswell/web
BASEMAP_ROOT=/opt/glasswell/basemap
# SB-07 2.3 zones. /data is the 1 TB volume; /srv/glasswell is an empty directory on the
# root disk, which is why the raw zone never went there (DR-06).
DATA_ROOT=/data
STAGING_ROOT="$DATA_ROOT/staging"
SCRATCH_ROOT="$DATA_ROOT/scratch"
PG_CONF_DIR=/etc/postgresql/16/main/conf.d
# File inclusion in pg_hba.conf and pg_ident.conf arrived in PostgreSQL 16, so the
# mechanism exists on this host and would silently not on 15. PG_CONF_DIR pins the major.
PG_ETC_DIR=/etc/postgresql/16/main
PG_IDENT_DROPIN_DIR="$PG_ETC_DIR/pg_ident.d"
PG_IDENT_MAP=glasswell
# Not under /etc/glasswell: that directory is 0700 root and martin runs as `martin`. The
# tile config carries no secret — its DSN has no password — so it does not belong there.
MARTIN_CONF_DIR=/etc/martin
CADDY_CONF_DIR=/etc/caddy
CADDY_BIN=/usr/local/bin/caddy
CADDY_ENV="$CADDY_CONF_DIR/cloudflare.env"
CADDY_USER=caddy
RUN_USER=glasswell
TMPFILES_DIR=/etc/tmpfiles.d
CLOUDFLARED_DIR=/etc/cloudflared
CLOUDFLARED_BIN=/usr/local/bin/cloudflared
TUNNEL_ID_FILE=/etc/cloudflared/tunnel-id

with_postgres=0
with_martin_config=0
with_caddy=0
with_cloudflared=0
enable_ingest=0
enable_c115b=0
enable_backup=0
for argument in "$@"; do
    case "$argument" in
        --with-postgres) with_postgres=1 ;;
        --with-martin-config) with_martin_config=1 ;;
        --with-caddy) with_caddy=1 ;;
        --with-cloudflared) with_cloudflared=1 ;;
        --enable-ingest) enable_ingest=1 ;;
        --enable-c115b) enable_c115b=1 ;;
        --enable-backup) enable_backup=1 ;;
        -h|--help)
            printf 'usage: %s [--with-postgres] [--with-martin-config] [--with-caddy] [--with-cloudflared] [--enable-ingest] [--enable-c115b] [--enable-backup]\n' "${0##*/}"
            exit 0
            ;;
        *)
            printf 'unknown argument: %s\n' "$argument" >&2
            exit 2
            ;;
    esac
done

[[ $EUID -eq 0 ]] || { printf 'install.sh must run as root\n' >&2; exit 1; }
id "$RUN_USER" >/dev/null || { printf 'user %s does not exist\n' "$RUN_USER" >&2; exit 1; }

install -d -o root -g root -m 0700 "$ETC_DIR"
install -d -o "$RUN_USER" -g "$RUN_USER" -m 0750 "$STATE_DIR"
# A long load and a deploy publish their progress here, so both exist before any job runs:
# a runner that cannot write its status leaves a job that can only be guessed at. Root's, not
# $RUN_USER's: every step runs as $RUN_USER, and `result: complete` is the one fact deploy.sh
# and `--after-job` trust, so the account being judged does not get to rewrite the verdict.
install -d -o root -g "$RUN_USER" -m 0750 "$RUNS_DIR"
install -d -o "$RUN_USER" -g "$RUN_USER" -m 0755 "$RUN_LOG_DIR"
install -d -o "$RUN_USER" -g "$RUN_USER" -m 0755 "$WEB_ROOT"
install -d -o "$RUN_USER" -g "$RUN_USER" -m 0755 "$BASEMAP_ROOT"

if [[ -d $DATA_ROOT ]]; then
    install -d -o "$RUN_USER" -g "$RUN_USER" -m 0750 "$STAGING_ROOT" "$SCRATCH_ROOT"
else
    printf '%s is not mounted; staging and scratch roots not created\n' "$DATA_ROOT" >&2
    exit 1
fi

# The owner key is generated here and never printed: it exists only inside app.env.
if [[ ! -f "$ETC_DIR/app.env" ]]; then
    (
        umask 077
        sed "s|^GLASSWELL_OWNER_KEY=.*|GLASSWELL_OWNER_KEY=$(openssl rand -hex 32)|" \
            "$INFRA_DIR/env/app.env.example" > "$ETC_DIR/app.env"
    )
    printf 'generated %s with a fresh owner key\n' "$ETC_DIR/app.env"
else
    printf 'kept existing %s\n' "$ETC_DIR/app.env"
fi
chown root:root "$ETC_DIR/app.env"
chmod 0600 "$ETC_DIR/app.env"

if ! grep -q '^GLASSWELL_OWNER_KEY=.\{16,\}' "$ETC_DIR/app.env"; then
    printf 'app.env carries no usable GLASSWELL_OWNER_KEY — the API would 403 every request\n' >&2
    exit 1
fi

# Generated in place and never echoed, like the owner key. Idempotent: an existing key is
# kept, because rotating it would invalidate every outstanding CSRF token.
# Substitute when the line exists, append when it does not. An app.env seeded before this
# release carries no GLASSWELL_CSRF_KEY line at all, and a bare `sed -i s|^...|` would match
# nothing and leave the guard below to abort the install.
if ! grep -q '^GLASSWELL_CSRF_KEY=.\{32,\}' "$ETC_DIR/app.env"; then
    (
        umask 077
        if grep -q '^GLASSWELL_CSRF_KEY=' "$ETC_DIR/app.env"; then
            command sed -i "s|^GLASSWELL_CSRF_KEY=.*|GLASSWELL_CSRF_KEY=$(openssl rand -hex 32)|" \
                "$ETC_DIR/app.env"
        else
            printf 'GLASSWELL_CSRF_KEY=%s\n' "$(openssl rand -hex 32)" >> "$ETC_DIR/app.env"
        fi
    )
    printf 'generated a fresh GLASSWELL_CSRF_KEY in %s\n' "$ETC_DIR/app.env"
fi

if ! grep -q '^GLASSWELL_CSRF_KEY=.\{32,\}' "$ETC_DIR/app.env"; then
    printf 'app.env carries no usable GLASSWELL_CSRF_KEY — CSRF could not be enforced\n' >&2
    exit 1
fi

# tmpfiles.d/glasswell.conf names this group, and systemd-tmpfiles fails the whole line on an
# unknown one — which would leave glasswell-api with nowhere to put its socket. Created here
# rather than under --with-caddy: the API has no TCP listener, so an install without Caddy has
# no way in either.
getent group "$CADDY_USER" >/dev/null || {
    groupadd --system "$CADDY_USER"
    printf 'created system group %s — it owns the group on the api socket directory\n' "$CADDY_USER"
}

install -o root -g root -m 0644 "$INFRA_DIR/tmpfiles.d/glasswell.conf" "$TMPFILES_DIR/glasswell.conf"
systemd-tmpfiles --create "$TMPFILES_DIR/glasswell.conf"
printf 'placed %s/glasswell.conf and created /run/glasswell\n' "$TMPFILES_DIR"

for unit in glasswell-api.service glasswell-ingest.service glasswell-ingest.timer \
            glasswell-c115b.service glasswell-c115b.timer \
            glasswell-status.service glasswell-status.timer \
            glasswell-lineage-retention.service glasswell-lineage-retention.timer \
            glasswell-alert@.service glasswell-backup.service glasswell-backup.timer \
            glasswell-restore-drill.service glasswell-restore-drill.timer \
            glasswell-cf-ranges.service glasswell-cf-ranges.timer \
            glasswell-scheduler.service glasswell-scheduler.timer; do
    install -o root -g root -m 0644 "$INFRA_DIR/systemd/$unit" "$UNIT_DIR/$unit"
done

# One protection service invokes each script by absolute path. The recovery drill has no unit —
# it is an operator-run procedure on a replacement host — and the durable writer is the helper
# the receipts are published through.
for script in glasswell-backup.sh glasswell-restore-drill.sh glasswell-recovery-drill.sh \
              glasswell-durable-write.py; do
    install -o root -g root -m 0755 "$INFRA_DIR/backup/$script" "$SBIN_DIR/$script"
done

# Every runbook's long step and every remote deploy step goes through this one, and verify.sh
# holds the installed copy equal to the tree.
install -o root -g root -m 0755 "$INFRA_DIR/bin/host-runner.sh" "$SBIN_DIR/host-runner.sh"

# The five ad-hoc runners of 2026-09-05, retired with the status files they wrote: `co-load` is
# the Colorado runbook's job name and the ad-hoc verdict under it refuses the first tracked run.
# Archived, never deleted — a load's own record is the evidence it happened. Never while it is
# live: a deploy lands during a load, and moving a running runner's status file takes the
# operator's poll path and the stamps its verdict is assembled from. Liveness is the unit that
# runs the script and the state the job published, never the shape of the document. Keyed on the
# script, so a job name the tracked runner reuses later is not this migration's business.
retire_adhoc_runs() {
    local archive="$RUNS_DIR/archive" script job status sidecar unit live
    local -a active_units
    # No -o: install.sh is root-only (line 65). -g, so reading the archive is not root-only,
    # which is what runbook-co-tier2.md tells an operator to do.
    command install -d -g "$RUN_USER" -m 0750 "$archive"

    active_units=()
    while read -r unit; do
        [[ -n $unit ]] && active_units+=("$unit")
    done < <(systemctl list-units --type=service --state=active --no-legend --plain --no-pager \
                2>/dev/null | awk '{print $1}')  # no systemd here means no live runner to find

    for script in co-load-runner.sh tx-step3-runner.sh tx-step3-resume-runner.sh \
                  tx-step3-resume2-runner.sh tx-step45-runner.sh; do
        [[ -f "$SBIN_DIR/$script" ]] || continue
        job=${script%-runner.sh}
        status="$RUNS_DIR/$job.json"

        live=""
        for unit in ${active_units[@]+"${active_units[@]}"}; do
            case "$(systemctl show "$unit" -p ExecStart --value 2>/dev/null)" in  # unloaded answers empty
                *"$SBIN_DIR/$script"*) live=$unit; break ;;
            esac
        done
        if [[ -z $live && -f $status ]]; then
            case "$(sed -n 's/.*"result":"\([^"]*\)".*/\1/p' "$status")" in
                running|waiting) live="$job.json is running" ;;
            esac
        fi
        if [[ -n $live ]]; then
            printf 'deferred: live (%s) — %s and its records stay for the next deploy\n' \
                "$live" "$script"
            continue
        fi

        command mv "$SBIN_DIR/$script" "$archive/$script"
        printf 'retired %s: archived at %s\n' "$script" "$archive/$script"
        for sidecar in "$RUNS_DIR/$job".*; do
            [[ -f $sidecar ]] || continue
            command mv "$sidecar" "$archive/${sidecar##*/}"
            printf 'retired %s: archived under %s\n' "${sidecar##*/}" "$archive"
        done
    done
}
retire_adhoc_runs

# The units this release retired, disabled and removed rather than left behind. verify.sh
# fails a deploy on a host unit that has no counterpart in the tree, which is how a retired
# unit that was only stopped takes the next deploy down. Shipping the mechanism empty is the
# point: the release that retires a unit adds its name here and nothing else changes.
RETIRED_UNITS=()
for unit in ${RETIRED_UNITS[@]+"${RETIRED_UNITS[@]}"}; do
    if [[ -f "$UNIT_DIR/$unit" ]] || systemctl list-unit-files "$unit" >/dev/null 2>&1; then
        systemctl disable --now "$unit" >/dev/null 2>&1 || true  # already gone is the goal, not an error
        command rm -f "$UNIT_DIR/$unit"
        printf 'retired %s: disabled and removed\n' "$unit"
    fi
done

command install -o root -g root -m 0755 "$INFRA_DIR/cloudflare/refresh-ranges.sh" \
    "$SBIN_DIR/refresh-ranges.sh"
command install -o root -g "$RUN_USER" -m 0644 "$INFRA_DIR/cloudflare/ip-ranges.txt" \
    "$ETC_DIR/cloudflare-ips.txt"

if [[ $with_postgres -eq 1 ]]; then
    if [[ -d $PG_CONF_DIR ]]; then
        install -o root -g root -m 0644 \
            "$INFRA_DIR/postgres/postgresql.conf.d/glasswell.conf" "$PG_CONF_DIR/glasswell.conf"
        printf 'placed %s/glasswell.conf — restart postgresql to apply\n' "$PG_CONF_DIR"
    else
        printf '%s does not exist; postgres tuning not placed\n' "$PG_CONF_DIR" >&2
        exit 1
    fi
fi

# The ident map that lets the root-run scheduler authenticate as glasswell_scheduler, placed
# on every run and not behind a flag: deploy.sh runs ./install.sh with no arguments, so a step
# behind --with-postgres never reaches the host. The tuning drop-in above is one-time
# provisioning and stays there; this is what the scheduler needs on every deploy. Two files
# move, because a map is inert unless the matching pg_hba line names it, and both are read
# from the postmaster's in-memory copy, so an edit is inert until the reload below.
[[ -d $PG_ETC_DIR ]] || {
    printf '%s does not exist: PostgreSQL is not installed here, and the scheduler cannot\n' \
        "$PG_ETC_DIR" >&2
    printf 'authenticate without its ident map\n' >&2
    exit 1
}
hba="$PG_ETC_DIR/pg_hba.conf"
ident="$PG_ETC_DIR/pg_ident.conf"
[[ -f $hba && -f $ident ]] || {
    printf '%s or %s is missing; the ident map was not placed\n' "$hba" "$ident" >&2
    exit 1
}
# Refuse BEFORE writing anything. A missing target line means the host does not
# authenticate the way this map assumes; two means an edit would pick one arbitrarily;
# one already carrying a different map means someone else owns that rule.
target_re='^[[:space:]]*local[[:space:]]+all[[:space:]]+all[[:space:]]+peer([[:space:]]|$)'
matches="$(grep -cE "$target_re" "$hba" || true)"  # grep exits 1 on zero matches
if [[ $matches -ne 1 ]]; then
    printf '%s holds %s local all all peer lines; expected exactly one\n' \
        "$hba" "$matches" >&2
    exit 1
fi
existing_map="$(grep -E "$target_re" "$hba" | grep -oE 'map=[A-Za-z0-9_]+' || true)"
if [[ -n $existing_map && $existing_map != "map=$PG_IDENT_MAP" ]]; then
    printf '%s already carries %s on the local all/all rule\n' "$hba" "$existing_map" >&2
    exit 1
fi

install -d -o root -g root -m 0755 "$PG_IDENT_DROPIN_DIR"
install -o root -g postgres -m 0640 "$INFRA_DIR/postgres/pg_ident.d/glasswell.conf" \
    "$PG_IDENT_DROPIN_DIR/glasswell.conf"
# Unquoted on purpose: an HBA or ident include takes a bare filename, and PostgreSQL reads the
# quotes of the postgresql.conf form as part of the name (v0.78 shipped the quoted form and every
# peer login but postgres was refused until it was corrected on the host).
include_line="include_if_exists pg_ident.d/glasswell.conf"
legacy_include="include_if_exists 'pg_ident.d/glasswell.conf'"
if grep -qxF "$legacy_include" "$ident"; then
    sed -i "s|^${legacy_include}\$|${include_line}|" "$ident"
    printf 'corrected the quoted pg_ident include line in %s\n' "$ident"
fi
if ! grep -qxF "$include_line" "$ident"; then
    printf '\n# glasswell: the root-to-role map the scheduler needs\n%s\n' \
        "$include_line" >> "$ident"
    printf 'added the pg_ident include line to %s\n' "$ident"
fi
if [[ -z $existing_map ]]; then
    # `@` and not `|`: the pattern carries an alternation, and a pipe delimiter ends
    # the s command inside it.
    command sed -i -E "s@$target_re@& map=$PG_IDENT_MAP@" "$hba"
    printf 'added map=%s to the local all/all rule in %s\n' "$PG_IDENT_MAP" "$hba"
fi

# The reload is what makes any of the above true. Without it the first tick fails peer
# authentication up to an hour after a deploy that exited 0, because the deploy starts
# the timer and not the service.
systemctl reload postgresql || {
    printf 'postgresql did not reload; the ident map is written but not live\n' >&2
    exit 1
}
# A malformed pg_hba.conf is tolerated on reload and fatal on restart, and --with-postgres
# tells the operator to restart for the tuning drop-in. Read PostgreSQL's own view of what
# it parsed rather than trusting the bytes on disk.
hba_errors="$(sudo -u postgres psql -tAc \
    "select count(*) from pg_hba_file_rules where error is not null")"
ident_errors="$(sudo -u postgres psql -tAc \
    "select count(*) from pg_ident_file_mappings where error is not null")"
if [[ $hba_errors != 0 || $ident_errors != 0 ]]; then
    printf 'postgres reports %s hba and %s ident parse errors after the reload\n' \
        "$hba_errors" "$ident_errors" >&2
    exit 1
fi
printf 'placed the %s ident map and reloaded postgresql — both files parse clean\n' \
    "$PG_IDENT_MAP"

# The scheduler's own control-plane connection. One line, no secret: peer auth over the
# socket, with the role named because a pg_ident map checks the requested database user
# rather than defaulting it from the OS user. db.env is deliberately not touched — three
# units under two other uids read it, and no generated value would be right for all three.
install -o root -g root -m 0600 /dev/null "$ETC_DIR/scheduler.env"
printf 'GLASSWELL_DSN=postgresql:///glasswell?host=/var/run/postgresql&user=glasswell_scheduler\n' \
    > "$ETC_DIR/scheduler.env"
printf 'wrote %s/scheduler.env — password-free socket DSN, root:root 0600\n' "$ETC_DIR"

if [[ $with_martin_config -eq 1 ]]; then
    install -d -o root -g root -m 0755 "$MARTIN_CONF_DIR"
    install -o root -g root -m 0644 "$INFRA_DIR/martin/config.yaml" "$MARTIN_CONF_DIR/config.yaml"
    install -d -o root -g root -m 0755 "$UNIT_DIR/martin.service.d"
    install -o root -g root -m 0644 "$INFRA_DIR/systemd/martin.service.d/glasswell-config.conf" \
        "$UNIT_DIR/martin.service.d/glasswell-config.conf"
    printf 'placed %s/config.yaml and the martin drop-in — restart martin to adopt it\n' \
        "$MARTIN_CONF_DIR"
    printf 'martin will fail to connect until migration 026 has created the PG role martin\n'
fi

if [[ $with_caddy -eq 1 ]]; then
    [[ -x $CADDY_BIN ]] || {
        printf '%s is missing — fetch the custom build first (infra/caddy/README.md)\n' \
            "$CADDY_BIN" >&2
        exit 1
    }
    "$CADDY_BIN" list-modules | grep -qx 'dns.providers.cloudflare' || {
        printf '%s carries no cloudflare DNS module — DNS-01 renewal cannot work\n' \
            "$CADDY_BIN" >&2
        exit 1
    }
    [[ -f $CADDY_ENV ]] || {
        printf '%s is missing — it holds CF_API_TOKEN and is never in the repository\n' \
            "$CADDY_ENV" >&2
        exit 1
    }
    env_mode="$(stat -c '%U:%G %a' "$CADDY_ENV")"
    [[ $env_mode == 'root:root 600' ]] || {
        printf '%s is %s, expected root:root 600\n' "$CADDY_ENV" "$env_mode" >&2
        exit 1
    }

    id "$CADDY_USER" >/dev/null 2>&1 || {  # the check is the condition; a missing user is the branch
        # -g explicitly: the group is created earlier for glasswell-api's socket, and useradd
        # would otherwise try to create one of the same name and fail.
        useradd --system --home-dir /var/lib/caddy --shell /usr/sbin/nologin \
            -g "$CADDY_USER" "$CADDY_USER"
        printf 'created system user %s\n' "$CADDY_USER"
    }
    install -d -o root -g root -m 0755 "$CADDY_CONF_DIR"
    install -d -o "$CADDY_USER" -g "$CADDY_USER" -m 0700 /var/lib/caddy
    install -d -o "$CADDY_USER" -g "$CADDY_USER" -m 0750 /var/log/caddy
    install -o root -g root -m 0644 "$INFRA_DIR/caddy/Caddyfile" "$CADDY_CONF_DIR/Caddyfile"
    install -o root -g root -m 0644 "$INFRA_DIR/systemd/caddy.service" "$UNIT_DIR/caddy.service"

    # Validated with the token in the environment, because the tls block reads it.
    (
        set -a
        # shellcheck disable=SC1090
        . "$CADDY_ENV"
        set +a
        "$CADDY_BIN" validate --config "$CADDY_CONF_DIR/Caddyfile"
    ) || { printf 'the Caddyfile does not validate; nothing was reloaded\n' >&2; exit 1; }
    # validate provisions the file logger as root, which leaves an access.log the service
    # user cannot open. Ownership, not truncation: the log is evidence.
    chown -R "$CADDY_USER:$CADDY_USER" /var/log/caddy
    printf 'placed %s/Caddyfile and caddy.service — validated\n' "$CADDY_CONF_DIR"
fi

systemctl daemon-reload
systemctl enable glasswell-api.service
# Operational visibility is part of the serving product, not an optional ingest or backup
# schedule. Activation waits until migrations complete so a newly installed collector cannot
# race the schema grant it needs; deploy.sh and the manual runbook start it afterwards.
systemctl enable glasswell-status.timer
printf 'enabled glasswell-status.timer — start it after migrations complete\n'
systemctl enable glasswell-lineage-retention.timer
printf 'enabled glasswell-lineage-retention.timer — start it after migrations complete\n'
# Installed since the tunnel landed but enabled by nothing, so the weekly refresh its own file
# header advertises had never once run and verify.sh only ever measured install.sh's own mtime.
systemctl enable glasswell-cf-ranges.timer
printf 'enabled glasswell-cf-ranges.timer — start it to arm the weekly range refresh\n'
# Armed on every run, like the three above. There is no --enable-scheduler flag on purpose: a
# flag deploy.sh does not pass is how the ident map was lost, and while every row the registry
# resolves is launch_mode=observe the tick computes a plan and launches nothing, so arming it
# costs an hourly read and changes nothing else.
systemctl enable glasswell-scheduler.timer
printf 'enabled glasswell-scheduler.timer — hourly; every row observes, so it launches nothing\n'

if [[ $with_caddy -eq 1 ]]; then
    systemctl enable caddy.service
    printf 'enabled caddy.service — start or reload it to serve https://glasswell.lab.rpx.sh\n'
fi

if [[ $enable_ingest -eq 1 ]]; then
    systemctl enable glasswell-ingest.timer
    printf 'enabled glasswell-ingest.timer — it will fetch from NDIC monthly\n'
else
    printf 'glasswell-ingest.timer installed but NOT enabled (--enable-ingest to arm it)\n'
fi

if [[ $enable_c115b -eq 1 ]]; then
    systemctl enable glasswell-c115b.timer
    printf 'enabled glasswell-c115b.timer — it will capture NM C-115B monthly\n'
else
    printf 'glasswell-c115b.timer installed but NOT enabled (--enable-c115b to arm it)\n'
fi

if [[ $enable_backup -eq 1 ]] || systemctl is-enabled --quiet glasswell-backup.timer; then
    systemctl enable glasswell-backup.timer glasswell-restore-drill.timer
    printf 'enabled nightly backup and weekly restore-drill timers (new or previously armed)\n'
else
    printf 'backup and restore-drill timers installed but NOT enabled (--enable-backup to arm them)\n'
fi

printf 'install complete. start with: systemctl start glasswell-api\n'

# The connector is placed only when asked for, and only when the owner has already created
# the tunnel and left its id and credentials on the host. Nothing here mints a credential:
# a tunnel secret in an installer is a tunnel secret in every log the installer writes to.
if [[ $with_cloudflared -eq 1 ]]; then
    [[ -x $CLOUDFLARED_BIN ]] || {
        printf '%s is missing — install the connector first (infra/README.md)\n' \
            "$CLOUDFLARED_BIN" >&2
        exit 1
    }
    [[ -f $TUNNEL_ID_FILE ]] || {
        printf '%s is missing — create the tunnel and write its id there first\n' \
            "$TUNNEL_ID_FILE" >&2
        exit 1
    }
    tunnel_id="$(command tr -d '[:space:]' < "$TUNNEL_ID_FILE")"
    [[ -n $tunnel_id ]] || {
        printf '%s is empty\n' "$TUNNEL_ID_FILE" >&2
        exit 1
    }
    [[ -f $CLOUDFLARED_DIR/$tunnel_id.json ]] || {
        printf '%s/%s.json is missing — it is the tunnel credential and is never in the repository\n' \
            "$CLOUDFLARED_DIR" "$tunnel_id" >&2
        exit 1
    }
    getent group cloudflared >/dev/null || groupadd --system cloudflared
    getent passwd cloudflared >/dev/null || \
        useradd --system --gid cloudflared --home-dir "$CLOUDFLARED_DIR" \
            --shell /usr/sbin/nologin cloudflared
    # The directory, not just the files in it: 0640 root:cloudflared is unreadable through a
    # 0700 root:root parent, and the connector fails with a bare "permission denied" naming
    # the file rather than the directory that actually refused.
    command chown root:cloudflared "$CLOUDFLARED_DIR"
    command chmod 0750 "$CLOUDFLARED_DIR"
    command chown root:cloudflared "$CLOUDFLARED_DIR/$tunnel_id.json"
    command chmod 0640 "$CLOUDFLARED_DIR/$tunnel_id.json"

    command sed "s|<tunnel-uuid>|$tunnel_id|g" "$INFRA_DIR/cloudflared/config.yml" \
        > "$CLOUDFLARED_DIR/config.yml"
    command chown root:cloudflared "$CLOUDFLARED_DIR/config.yml"
    command chmod 0640 "$CLOUDFLARED_DIR/config.yml"
    command install -o root -g root -m 0644 "$INFRA_DIR/systemd/cloudflared.service" \
        "$UNIT_DIR/cloudflared.service"
    command install -o root -g root -m 0644 \
        "$INFRA_DIR/cloudflared/99-cloudflared-udp.conf" \
        /etc/sysctl.d/99-cloudflared-udp.conf
    sysctl --quiet --load /etc/sysctl.d/99-cloudflared-udp.conf \
        || printf 'warning: could not apply UDP buffer sysctls; they take effect at next boot\n' >&2

    # Placing the connector *is* the decision to be public, so the flag that turns on the
    # public refusals is set here rather than by an operator remembering a sed line. Left
    # apart, an instance could serve the internet with GLASSWELL_ALLOW_ANON=1 and the
    # startup abort would never fire.
    if grep -q '^GLASSWELL_PUBLIC=' "$ETC_DIR/app.env"; then
        command sed -i 's|^GLASSWELL_PUBLIC=.*|GLASSWELL_PUBLIC=1|' "$ETC_DIR/app.env"
    else
        printf 'GLASSWELL_PUBLIC=1\n' >> "$ETC_DIR/app.env"
    fi
    printf 'placed %s/config.yml and the connector unit; GLASSWELL_PUBLIC=1\n' "$CLOUDFLARED_DIR"
fi
