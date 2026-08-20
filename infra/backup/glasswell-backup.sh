#!/bin/bash
# glasswell-backup — SB-06 section 7.2 Layer B: nightly logical backup of the
# glasswell database plus a push of the raw zone to forge.
set -uo pipefail

DB="${DB:-glasswell}"
PGDUMP_DIR="${PGDUMP_DIR:-/data/backups/pg}"
RAW_DIR="${RAW_DIR:-/data/raw}"
RETAIN_DAYS="${RETAIN_DAYS:-14}"
FORGE="${FORGE:-root@192.168.2.205}"
BACKUP_KEY="${BACKUP_KEY:-/root/.ssh/id_glasswell_backup}"

SSH_CMD="ssh -i $BACKUP_KEY -o BatchMode=yes -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=15"

log() { echo "$*"; }  # stdout is captured by the journal under systemd
fail() { log "FAIL: $*"; exit 1; }

ts=$(date -u +%Y%m%dT%H%M%SZ)
# root:postgres 0750 so pg_restore (which runs as postgres) can read a dump directly;
# the parent must be traversable by postgres or the 0750 leaf is unreachable.
install -d -m 755 "$(dirname "$PGDUMP_DIR")" || fail "cannot create $(dirname "$PGDUMP_DIR")"
install -d -m 750 -o root -g postgres "$PGDUMP_DIR" || fail "cannot create $PGDUMP_DIR"

dump="$PGDUMP_DIR/glasswell-$ts.dump"
globals="$PGDUMP_DIR/globals-$ts.sql"

# Write to .partial and rename only after the archive verifies, so a crashed run
# never leaves a truncated file that looks like a good backup (mirrors section 3.3).
runuser -u postgres -- pg_dump -Fc -Z6 -d "$DB" > "$dump.partial" || fail "pg_dump $DB"
pg_restore -l "$dump.partial" > /dev/null 2>&1 || fail "pg_restore -l rejected the archive"
chown root:postgres "$dump.partial" && chmod 640 "$dump.partial"
mv "$dump.partial" "$dump" || fail "rename $dump"

runuser -u postgres -- pg_dumpall --globals-only > "$globals.partial" || fail "pg_dumpall --globals-only"
[ -s "$globals.partial" ] || fail "globals dump is empty"
chown root:postgres "$globals.partial" && chmod 640 "$globals.partial"
mv "$globals.partial" "$globals" || fail "rename $globals"

log "dumped $(stat -c %s "$dump") bytes -> $dump"

find "$PGDUMP_DIR" -maxdepth 1 -type f \
	\( -name 'glasswell-*.dump' -o -name 'globals-*.sql' -o -name '*.partial' \) \
	-mtime +"$RETAIN_DAYS" -delete || log "WARN: prune pass reported an error"
kept=$(find "$PGDUMP_DIR" -maxdepth 1 -type f -name 'glasswell-*.dump' | wc -l)
log "retention ${RETAIN_DAYS}d: ${kept} dump(s) kept locally"

rsync -aH --delete -e "$SSH_CMD" "$PGDUMP_DIR/" "$FORGE:pgdump/" </dev/null \
	|| fail "rsync pgdump -> $FORGE"
log "pushed pgdump/ to $FORGE"

if [ -d "$RAW_DIR" ]; then
	rsync -aH --delete -e "$SSH_CMD" "$RAW_DIR/" "$FORGE:raw/" </dev/null \
		|| fail "rsync raw zone -> $FORGE"
	log "pushed raw zone ($(du -sh "$RAW_DIR" | cut -f1)) to $FORGE"
else
	log "WARN: $RAW_DIR does not exist, raw-zone push skipped"
fi

log "OK: backup complete ($ts)"
