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

snapshot_input=""
snapshot_output=""
snapshot_pid=""

close_snapshot_session() {
	if [[ -n $snapshot_input ]]; then
		exec {snapshot_input}>&-
		snapshot_input=""
	fi
	if [[ -n $snapshot_output ]]; then
		exec {snapshot_output}<&-
		snapshot_output=""
	fi
	if [[ -n $snapshot_pid ]] && kill -0 "$snapshot_pid" 2>/dev/null; then
		kill "$snapshot_pid" 2>/dev/null || true
		wait "$snapshot_pid" 2>/dev/null || true
	fi
	snapshot_pid=""
}

trap close_snapshot_session EXIT

created_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
ts=$(date -u --date="$created_at" +%Y%m%dT%H%M%SZ)
# root:postgres 0750 so pg_restore (which runs as postgres) can read a dump directly;
# the parent must be traversable by postgres or the 0750 leaf is unreachable.
install -d -m 755 "$(dirname "$PGDUMP_DIR")" || fail "cannot create $(dirname "$PGDUMP_DIR")"
install -d -m 750 -o root -g postgres "$PGDUMP_DIR" || fail "cannot create $PGDUMP_DIR"
exec {backup_lock}>"$PGDUMP_DIR/.glasswell-backup.lock" \
	|| fail "open backup invocation lock"
flock -n "$backup_lock" || fail "another backup invocation is active"

dump="$PGDUMP_DIR/glasswell-$ts.dump"
manifest="$PGDUMP_DIR/glasswell-$ts.manifest.json"
globals="$PGDUMP_DIR/globals-$ts.sql"
[[ ! -e $dump && ! -e $manifest && ! -e $globals ]] \
	|| fail "backup generation $ts already exists"

# Keep an exported read-only snapshot open while both pg_dump and the restore-proof counts
# observe it. The sidecar therefore describes the dump's vintage, not a later mutable source.
coproc SNAPSHOT_SESSION {
	runuser -u postgres -- psql --no-psqlrc --set=ON_ERROR_STOP=1 \
		--tuples-only --no-align --quiet --dbname "$DB"
}
snapshot_pid=$SNAPSHOT_SESSION_PID
exec {snapshot_input}>&"${SNAPSHOT_SESSION[1]}"
exec {snapshot_output}<&"${SNAPSHOT_SESSION[0]}"
printf '%s\n' \
	"BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;" \
	"SELECT pg_export_snapshot();" >&"$snapshot_input" \
	|| fail "start exported database snapshot"
IFS= read -r snapshot_id <&"$snapshot_output" \
	|| fail "read exported database snapshot"
[[ $snapshot_id =~ ^[[:xdigit:]]{8}-[[:xdigit:]]{8}-[[:xdigit:]]+$ ]] \
	|| fail "database returned an invalid snapshot id"

# Write to .partial and rename only after the archive and its exact-vintage manifest verify,
# so a crashed run never leaves a truncated file that looks like a good backup.
runuser -u postgres -- pg_dump -Fc -Z6 --snapshot="$snapshot_id" -d "$DB" \
	> "$dump.partial" || fail "pg_dump $DB"

manifest_query="SELECT json_build_object('source_schema_version',(SELECT coalesce(max(version),0) FROM public.schema_migrations),'critical_row_counts',json_build_object('lineage.manifests',(SELECT count(*) FROM lineage.manifests),'canonical.wells_latest',(SELECT count(*) FROM canonical.wells_latest),'canonical.production_monthly',(SELECT count(*) FROM canonical.production_monthly),'marts.nd_wells_tile',(SELECT count(*) FROM marts.nd_wells_tile)))::text;"
printf '%s\n' "$manifest_query" "COMMIT;" '\q' >&"$snapshot_input" \
	|| fail "query dump-vintage manifest"
IFS= read -r snapshot_payload <&"$snapshot_output" \
	|| fail "read dump-vintage manifest"
exec {snapshot_input}>&-
snapshot_input=""
if ! wait "$snapshot_pid"; then
	snapshot_pid=""
	fail "database snapshot session"
fi
snapshot_pid=""
exec {snapshot_output}<&-
snapshot_output=""

pg_restore -l "$dump.partial" > /dev/null 2>&1 || fail "pg_restore -l rejected the archive"
dump_bytes=$(stat -c %s "$dump.partial") || fail "stat $dump.partial"
dump_sha256=$(sha256sum "$dump.partial") || fail "sha256sum $dump.partial"
dump_sha256=${dump_sha256%% *}
SNAPSHOT_PAYLOAD="$snapshot_payload" DUMP_NAME="${dump##*/}" DUMP_BYTES="$dump_bytes" \
	DUMP_SHA256="$dump_sha256" BACKUP_DATABASE="$DB" BACKUP_CREATED_AT="$created_at" \
	/usr/bin/python3 - "$manifest.partial" <<'PY' || fail "build $manifest.partial"
import json
import os
import sys
from datetime import datetime
from pathlib import Path

payload = json.loads(os.environ["SNAPSHOT_PAYLOAD"])
expected_datasets = {
    "lineage.manifests",
    "canonical.wells_latest",
    "canonical.production_monthly",
    "marts.nd_wells_tile",
}
if set(payload) != {"source_schema_version", "critical_row_counts"}:
    raise SystemExit("snapshot payload has unexpected fields")
schema_version = payload["source_schema_version"]
counts = payload["critical_row_counts"]
if not isinstance(schema_version, int) or schema_version < 0:
    raise SystemExit("snapshot schema version is invalid")
if not isinstance(counts, dict) or set(counts) != expected_datasets:
    raise SystemExit("snapshot critical row counts are incomplete")
if any(not isinstance(value, int) or isinstance(value, bool) or value <= 0 for value in counts.values()):
    raise SystemExit("snapshot critical row count is invalid")
created_at = os.environ["BACKUP_CREATED_AT"]
if datetime.fromisoformat(created_at.replace("Z", "+00:00")).utcoffset() is None:
    raise SystemExit("backup timestamp lacks an offset")
dump_bytes = int(os.environ["DUMP_BYTES"])
dump_sha256 = os.environ["DUMP_SHA256"]
if dump_bytes <= 0 or len(dump_sha256) != 64:
    raise SystemExit("dump identity is invalid")
manifest = {
    "manifest_version": 1,
    "database": os.environ["BACKUP_DATABASE"],
    "created_at": created_at,
    "dump": {
        "name": os.environ["DUMP_NAME"],
        "sha256": dump_sha256,
        "bytes": dump_bytes,
    },
    "source_schema_version": schema_version,
    "critical_row_counts": counts,
}
Path(sys.argv[1]).write_text(
    json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n",
    encoding="utf-8",
)
PY
chown root:postgres "$dump.partial" || fail "chown $dump.partial"
chmod 640 "$dump.partial" || fail "chmod $dump.partial"
chown root:postgres "$manifest.partial" || fail "chown $manifest.partial"
chmod 640 "$manifest.partial" || fail "chmod $manifest.partial"

runuser -u postgres -- pg_dumpall --globals-only > "$globals.partial" || fail "pg_dumpall --globals-only"
[ -s "$globals.partial" ] || fail "globals dump is empty"
chown root:postgres "$globals.partial" || fail "chown $globals.partial"
chmod 640 "$globals.partial" || fail "chmod $globals.partial"
mv "$globals.partial" "$globals" || fail "rename $globals"
mv "$dump.partial" "$dump" || fail "rename $dump"
# The manifest is the generation's commit marker. Restore discovery starts from manifests, so
# an interrupted promotion can leave an ignored orphan but never expose a cross-wired pair.
mv "$manifest.partial" "$manifest" || fail "rename $manifest"

log "dumped $dump_bytes bytes with exact-vintage manifest -> $dump"

find "$PGDUMP_DIR" -maxdepth 1 -type f \
	\( -name 'glasswell-*.dump' -o -name 'glasswell-*.manifest.json' \
	   -o -name 'globals-*.sql' -o -name '*.partial' \) \
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
