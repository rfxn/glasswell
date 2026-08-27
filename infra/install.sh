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

with_postgres=0
with_martin_config=0
with_caddy=0
enable_ingest=0
enable_c115b=0
enable_backup=0
for argument in "$@"; do
    case "$argument" in
        --with-postgres) with_postgres=1 ;;
        --with-martin-config) with_martin_config=1 ;;
        --with-caddy) with_caddy=1 ;;
        --enable-ingest) enable_ingest=1 ;;
        --enable-c115b) enable_c115b=1 ;;
        --enable-backup) enable_backup=1 ;;
        -h|--help)
            printf 'usage: %s [--with-postgres] [--with-martin-config] [--with-caddy] [--enable-ingest] [--enable-c115b] [--enable-backup]\n' "${0##*/}"
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
            glasswell-alert@.service glasswell-backup.service glasswell-backup.timer; do
    install -o root -g root -m 0644 "$INFRA_DIR/systemd/$unit" "$UNIT_DIR/$unit"
done

# glasswell-backup.service calls these by absolute path.
for script in glasswell-backup.sh glasswell-restore-drill.sh; do
    install -o root -g root -m 0755 "$INFRA_DIR/backup/$script" "$SBIN_DIR/$script"
done

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

if [[ $enable_backup -eq 1 ]]; then
    systemctl enable glasswell-backup.timer
    printf 'enabled glasswell-backup.timer — nightly, and it pushes to forge over ssh\n'
else
    printf 'glasswell-backup.timer installed but NOT enabled (--enable-backup to arm it)\n'
fi

printf 'install complete. start with: systemctl start glasswell-api\n'
