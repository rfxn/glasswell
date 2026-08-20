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
RUN_USER=glasswell

with_postgres=0
enable_ingest=0
enable_backup=0
for argument in "$@"; do
    case "$argument" in
        --with-postgres) with_postgres=1 ;;
        --enable-ingest) enable_ingest=1 ;;
        --enable-backup) enable_backup=1 ;;
        -h|--help)
            printf 'usage: %s [--with-postgres] [--enable-ingest] [--enable-backup]\n' "${0##*/}"
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

for unit in glasswell-api.service glasswell-ingest.service glasswell-ingest.timer \
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

systemctl daemon-reload
systemctl enable glasswell-api.service

if [[ $enable_ingest -eq 1 ]]; then
    systemctl enable glasswell-ingest.timer
    printf 'enabled glasswell-ingest.timer — it will fetch from NDIC monthly\n'
else
    printf 'glasswell-ingest.timer installed but NOT enabled (--enable-ingest to arm it)\n'
fi

if [[ $enable_backup -eq 1 ]]; then
    systemctl enable glasswell-backup.timer
    printf 'enabled glasswell-backup.timer — nightly, and it pushes to forge over ssh\n'
else
    printf 'glasswell-backup.timer installed but NOT enabled (--enable-backup to arm it)\n'
fi

printf 'install complete. start with: systemctl start glasswell-api\n'
