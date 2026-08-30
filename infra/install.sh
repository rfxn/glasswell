#!/usr/bin/env bash
# Place the glasswell host configuration. Idempotent: safe to re-run after every deploy.
set -euo pipefail

INFRA_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ETC_DIR=/etc/glasswell
STATE_DIR=/var/lib/glasswell
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
            glasswell-cf-ranges.service glasswell-cf-ranges.timer; do
    install -o root -g root -m 0644 "$INFRA_DIR/systemd/$unit" "$UNIT_DIR/$unit"
done

# One protection service invokes each script by absolute path. The recovery drill has no unit —
# it is an operator-run procedure on a replacement host — and the durable writer is the helper
# the receipts are published through.
for script in glasswell-backup.sh glasswell-restore-drill.sh glasswell-recovery-drill.sh \
              glasswell-durable-write.py; do
    install -o root -g root -m 0755 "$INFRA_DIR/backup/$script" "$SBIN_DIR/$script"
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
