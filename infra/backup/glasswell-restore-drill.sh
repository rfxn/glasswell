#!/bin/bash
# Restore the newest production dump into a scratch database, prove representative reads,
# publish a sanitized durable result, and remove the scratch database on every exit path.
set -uo pipefail

PGDUMP_DIR="${PGDUMP_DIR:-/data/backups/pg}"
RESULT_PATH="${RESTORE_RESULT_PATH:-/var/lib/glasswell-restore-drill/result.json}"
RESULT_UID="${RESTORE_RESULT_UID:-root}"
RESULT_GID="${RESTORE_RESULT_GID:-glasswell}"
EXPECTED_DUMP_OWNER="${EXPECTED_DUMP_OWNER:-root}"
EXPECTED_DUMP_GROUP="${EXPECTED_DUMP_GROUP:-postgres}"
SOURCE=glasswell

started_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
started_epoch=$(date -u +%s)
SCRATCH="glasswell_restore_${started_epoch}_$$_${RANDOM}"
result=failed
failure_detail=drill_interrupted
dump_name=""
dump_sha256=""
dump_bytes=""
dump_created_at=""
source_schema_version=""
restored_schema_version=""
row_comparisons=""
read_assertions=""
scratch_removed=false

log() { printf '%s\n' "$*"; }

fail() {
	failure_detail=$1
	log "FAIL: $2"
	exit 1
}

psql_value() {
	local database=$1
	local statement=$2
	runuser -u postgres -- psql --no-psqlrc --set=ON_ERROR_STOP=1 \
		--tuples-only --no-align --dbname "$database" --command "$statement"
}

drop_and_verify_scratch() {
	local remaining
	psql_value postgres "DROP DATABASE IF EXISTS $SCRATCH WITH (FORCE);" >/dev/null 2>&1 \
		|| return 1
	remaining=$(psql_value postgres \
		"SELECT count(*) FROM pg_database WHERE datname = '$SCRATCH';" 2>/dev/null) \
		|| return 1
	remaining=${remaining//[[:space:]]/}
	[[ $remaining == 0 ]]
}

append_row_comparison() {
	local dataset=$1
	local source_rows=$2
	local restored_rows=$3
	printf -v row_comparisons '%s%s\t%s\t%s\n' \
		"$row_comparisons" "$dataset" "$source_rows" "$restored_rows"
}

append_read_assertion() {
	local assertion_id=$1
	local passed=$2
	printf -v read_assertions '%s%s\t%s\n' "$read_assertions" "$assertion_id" "$passed"
}

write_result() {
	local completed_at=$1
	local duration_seconds=$2
	RESTORE_RESULT="$result" \
	RESTORE_FAILURE_DETAIL="$failure_detail" \
	RESTORE_DUMP_NAME="$dump_name" \
	RESTORE_DUMP_SHA256="$dump_sha256" \
	RESTORE_DUMP_BYTES="$dump_bytes" \
	RESTORE_DUMP_CREATED_AT="$dump_created_at" \
	RESTORE_STARTED_AT="$started_at" \
	RESTORE_COMPLETED_AT="$completed_at" \
	RESTORE_DURATION_SECONDS="$duration_seconds" \
	RESTORE_SOURCE_SCHEMA_VERSION="$source_schema_version" \
	RESTORE_RESTORED_SCHEMA_VERSION="$restored_schema_version" \
	RESTORE_ROW_COMPARISONS="$row_comparisons" \
	RESTORE_READ_ASSERTIONS="$read_assertions" \
	RESTORE_SCRATCH_REMOVED="$scratch_removed" \
	RESTORE_RESULT_UID="$RESULT_UID" \
	RESTORE_RESULT_GID="$RESULT_GID" \
	/usr/bin/python3 - "$RESULT_PATH" <<'PY'
import grp
import json
import os
import pwd
import re
import stat
import sys
import tempfile
from pathlib import Path

target = Path(sys.argv[1])
if not target.is_absolute():
    raise SystemExit("restore result path must be absolute")
parent = target.parent
parent_metadata = parent.lstat()
if not stat.S_ISDIR(parent_metadata.st_mode) or parent.is_symlink():
    raise SystemExit("restore result parent is unsafe")
if parent.resolve(strict=True) != parent:
    raise SystemExit("restore result parent has a symlink component")

uid_value = os.environ["RESTORE_RESULT_UID"]
gid_value = os.environ["RESTORE_RESULT_GID"]
uid = int(uid_value) if uid_value.isdecimal() else pwd.getpwnam(uid_value).pw_uid
gid = int(gid_value) if gid_value.isdecimal() else grp.getgrnam(gid_value).gr_gid

try:
    existing = target.lstat()
except FileNotFoundError:
    existing = None
if existing is not None:
    if not stat.S_ISREG(existing.st_mode) or target.is_symlink() or existing.st_nlink != 1:
        raise SystemExit("restore result target is unsafe")
    if (existing.st_uid, existing.st_gid, stat.S_IMODE(existing.st_mode)) != (uid, gid, 0o640):
        raise SystemExit("restore result target ownership or mode is unsafe")


def optional_integer(name: str) -> int | None:
    value = os.environ[name]
    if not value:
        return None
    if not value.isdecimal():
        raise SystemExit(f"invalid {name}")
    return int(value)


dump_name = os.environ["RESTORE_DUMP_NAME"] or None
dump_sha256 = os.environ["RESTORE_DUMP_SHA256"] or None
dump_bytes = optional_integer("RESTORE_DUMP_BYTES")
dump_created_at = os.environ["RESTORE_DUMP_CREATED_AT"] or None
if dump_name is not None and not re.fullmatch(r"glasswell-\d{8}T\d{6}Z\.dump", dump_name):
    raise SystemExit("invalid dump name")
if dump_sha256 is not None and not re.fullmatch(r"[0-9a-f]{64}", dump_sha256):
    raise SystemExit("invalid dump hash")
if any(value is None for value in (dump_name, dump_sha256, dump_bytes, dump_created_at)):
    dump = None
    if any(value is not None for value in (dump_name, dump_sha256, dump_bytes, dump_created_at)):
        raise SystemExit("partial dump identity")
else:
    dump = {
        "name": dump_name,
        "sha256": dump_sha256,
        "bytes": dump_bytes,
        "created_at": dump_created_at,
    }

row_comparisons = []
for line in os.environ["RESTORE_ROW_COMPARISONS"].splitlines():
    dataset, source_rows, restored_rows = line.split("\t")
    if dataset not in {
        "lineage.manifests",
        "canonical.wells_latest",
        "canonical.production_monthly",
        "marts.nd_wells_tile",
    }:
        raise SystemExit("invalid row-comparison dataset")
    if not source_rows.isdecimal() or not restored_rows.isdecimal():
        raise SystemExit("invalid row-comparison count")
    row_comparisons.append(
        {
            "dataset": dataset,
            "source_rows": int(source_rows),
            "restored_rows": int(restored_rows),
            "match": source_rows == restored_rows,
        }
    )

read_assertions = []
for line in os.environ["RESTORE_READ_ASSERTIONS"].splitlines():
    assertion_id, passed = line.split("\t")
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", assertion_id) or passed not in {"true", "false"}:
        raise SystemExit("invalid read assertion")
    read_assertions.append({"id": assertion_id, "passed": passed == "true"})

result = os.environ["RESTORE_RESULT"]
failure_detail = os.environ["RESTORE_FAILURE_DETAIL"] or None
if result not in {"passed", "failed"}:
    raise SystemExit("invalid restore result")
if failure_detail is not None and not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", failure_detail):
    raise SystemExit("invalid failure detail")
if (result == "passed") != (failure_detail is None):
    raise SystemExit("inconsistent restore result")

source_schema = optional_integer("RESTORE_SOURCE_SCHEMA_VERSION")
restored_schema = optional_integer("RESTORE_RESTORED_SCHEMA_VERSION")
payload = {
    "result_version": 1,
    "result": result,
    "failure_detail": failure_detail,
    "dump": dump,
    "started_at": os.environ["RESTORE_STARTED_AT"],
    "completed_at": os.environ["RESTORE_COMPLETED_AT"],
    "duration_seconds": optional_integer("RESTORE_DURATION_SECONDS"),
    "source_schema_version": source_schema,
    "restored_schema_version": restored_schema,
    "schema_match": (
        source_schema == restored_schema
        if source_schema is not None and restored_schema is not None
        else None
    ),
    "critical_row_counts": row_comparisons,
    "representative_reads": read_assertions,
    "scratch_removed": os.environ["RESTORE_SCRATCH_REMOVED"] == "true",
}

descriptor, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", dir=parent)
temporary = Path(temporary_name)
try:
    os.fchmod(descriptor, 0o640)
    os.fchown(descriptor, uid, gid)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, sort_keys=True, separators=(",", ":"))
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, target)
    directory = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
except BaseException:
    try:
        os.close(descriptor)
    except OSError:
        pass
    temporary.unlink(missing_ok=True)
    raise
PY
}

finish() {
	local exit_code=$?
	local completed_at completed_epoch duration_seconds
	trap - EXIT HUP INT TERM

	if drop_and_verify_scratch; then
		scratch_removed=true
	else
		scratch_removed=false
		result=failed
		# scratch_removed carries the leak; failure_detail keeps the cause that came first,
		# so a cleanup miss never hides an unrestorable dump.
		[[ -n $failure_detail ]] || failure_detail=scratch_cleanup_failed
		exit_code=1
		log "FAIL: scratch database cleanup could not be verified"
	fi

	if [[ $exit_code -ne 0 ]]; then
		result=failed
	elif [[ $result != passed ]]; then
		result=failed
		failure_detail=drill_interrupted
		exit_code=1
	fi

	completed_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
	completed_epoch=$(date -u +%s)
	duration_seconds=$((completed_epoch - started_epoch))
	if ! write_result "$completed_at" "$duration_seconds"; then
		log "FAIL: durable restore result could not be written"
		exit_code=1
	fi

	if [[ $exit_code -eq 0 ]]; then
		log "OK: restore drill passed; durable proof recorded"
	fi
	exit "$exit_code"
}

trap finish EXIT
trap 'failure_detail=drill_interrupted; exit 129' HUP
trap 'failure_detail=drill_interrupted; exit 130' INT
trap 'failure_detail=drill_interrupted; exit 143' TERM

[[ -d $PGDUMP_DIR && ! -L $PGDUMP_DIR ]] \
	|| fail unsafe_dump_directory "dump directory is missing or unsafe"
[[ $(realpath -e -- "$PGDUMP_DIR") == "$PGDUMP_DIR" ]] \
	|| fail unsafe_dump_directory "dump directory contains a symlink component"

newest=""
selected_manifest=""
newest_timestamp=0
shopt -s nullglob
for candidate_manifest in "$PGDUMP_DIR"/glasswell-*.manifest.json; do
	[[ -f $candidate_manifest && ! -L $candidate_manifest ]] \
		|| fail unsafe_dump_manifest "a dump manifest is not a regular file"
	manifest_name=${candidate_manifest##*/}
	[[ $manifest_name =~ ^glasswell-[0-9]{8}T[0-9]{6}Z\.manifest\.json$ ]] \
		|| fail unsafe_dump_manifest "a dump manifest has an invalid name"
	read -r manifest_owner manifest_group manifest_mode manifest_links manifest_timestamp \
		< <(stat -c '%U %G %a %h %Y' -- "$candidate_manifest") \
		|| fail dump_stat_failed "dump manifest metadata could not be read"
	[[ $manifest_owner == "$EXPECTED_DUMP_OWNER" && $manifest_group == "$EXPECTED_DUMP_GROUP" ]] \
		|| fail unsafe_dump_manifest "a dump manifest has unexpected ownership"
	(( (8#$manifest_mode & 0022) == 0 )) \
		|| fail unsafe_dump_manifest "a dump manifest is group- or world-writable"
	[[ $manifest_links == 1 ]] \
		|| fail unsafe_dump_manifest "a dump manifest has multiple hard links"
	candidate=${candidate_manifest%.manifest.json}.dump
	[[ -e $candidate ]] \
		|| fail manifest_dump_missing "a committed dump manifest has no archive"
	[[ -f $candidate && ! -L $candidate ]] \
		|| fail unsafe_dump_candidate "a dump candidate is not a regular file"
	candidate_name=${candidate##*/}
	[[ $candidate_name =~ ^glasswell-[0-9]{8}T[0-9]{6}Z\.dump$ ]] \
		|| fail unsafe_dump_candidate "a dump candidate has an invalid name"
	read -r candidate_owner candidate_group candidate_mode candidate_links \
		< <(stat -c '%U %G %a %h' -- "$candidate") \
		|| fail dump_stat_failed "dump metadata could not be read"
	[[ $candidate_owner == "$EXPECTED_DUMP_OWNER" && $candidate_group == "$EXPECTED_DUMP_GROUP" ]] \
		|| fail unsafe_dump_candidate "a dump candidate has unexpected ownership"
	(( (8#$candidate_mode & 0022) == 0 )) \
		|| fail unsafe_dump_candidate "a dump candidate is group- or world-writable"
	[[ $candidate_links == 1 ]] \
		|| fail unsafe_dump_candidate "a dump candidate has multiple hard links"
	if (( manifest_timestamp > newest_timestamp )); then
		newest_timestamp=$manifest_timestamp
		newest=$candidate
		selected_manifest=$candidate_manifest
	fi
done
[[ -n $newest ]] || fail no_dump_found "no complete production dump was found"

selected_name=${newest##*/}
selected_bytes=$(stat -c %s -- "$newest") || fail dump_stat_failed "dump size could not be read"
(( selected_bytes > 0 )) || fail empty_dump "the newest dump is empty"
selected_sha256=$(sha256sum -- "$newest") || fail dump_hash_failed "dump hash could not be computed"
selected_sha256=${selected_sha256%% *}
[[ $selected_sha256 =~ ^[0-9a-f]{64}$ ]] || fail dump_hash_failed "dump hash was invalid"
runuser -u postgres -- test -r "$newest" \
	|| fail dump_unreadable "the postgres identity cannot read the dump"
runuser -u postgres -- pg_restore -l "$newest" >/dev/null 2>&1 \
	|| fail dump_archive_invalid "the dump archive catalogue is invalid"

[[ -e $selected_manifest ]] \
	|| fail no_dump_manifest "the selected dump has no exact-vintage manifest"
[[ -f $selected_manifest && ! -L $selected_manifest ]] \
	|| fail unsafe_dump_manifest "the dump manifest is not a regular file"
read -r manifest_owner manifest_group manifest_mode manifest_links \
	< <(stat -c '%U %G %a %h' -- "$selected_manifest") \
	|| fail unsafe_dump_manifest "dump manifest metadata could not be read"
[[ $manifest_owner == "$EXPECTED_DUMP_OWNER" && $manifest_group == "$EXPECTED_DUMP_GROUP" ]] \
	|| fail unsafe_dump_manifest "the dump manifest has unexpected ownership"
(( (8#$manifest_mode & 0022) == 0 )) \
	|| fail unsafe_dump_manifest "the dump manifest is group- or world-writable"
[[ $manifest_links == 1 ]] \
	|| fail unsafe_dump_manifest "the dump manifest has multiple hard links"
runuser -u postgres -- test -r "$selected_manifest" \
	|| fail unsafe_dump_manifest "the postgres identity cannot read the dump manifest"

manifest_output=$(/usr/bin/python3 - "$selected_manifest" "$selected_name" "$selected_sha256" \
	"$selected_bytes" "$SOURCE" <<'PY'
import json
import re
import sys
from datetime import datetime
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
expected_keys = {
    "manifest_version",
    "database",
    "created_at",
    "dump",
    "source_schema_version",
    "critical_row_counts",
}
expected_datasets = (
    "lineage.manifests",
    "canonical.wells_latest",
    "canonical.production_monthly",
    "marts.nd_wells_tile",
)
if not isinstance(payload, dict) or set(payload) != expected_keys:
    raise SystemExit("manifest fields are invalid")
if payload["manifest_version"] != 1 or payload["database"] != sys.argv[5]:
    raise SystemExit("manifest identity is invalid")
created_at = payload["created_at"]
if not isinstance(created_at, str):
    raise SystemExit("manifest timestamp is invalid")
parsed = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
if parsed.utcoffset() is None:
    raise SystemExit("manifest timestamp lacks an offset")
dump = payload["dump"]
if not isinstance(dump, dict) or set(dump) != {"name", "sha256", "bytes"}:
    raise SystemExit("manifest dump identity is invalid")
if dump != {"name": sys.argv[2], "sha256": sys.argv[3], "bytes": int(sys.argv[4])}:
    raise SystemExit("manifest does not identify the selected dump")
if not re.fullmatch(r"[0-9a-f]{64}", dump["sha256"]):
    raise SystemExit("manifest dump hash is invalid")
schema_version = payload["source_schema_version"]
if not isinstance(schema_version, int) or isinstance(schema_version, bool) or schema_version < 0:
    raise SystemExit("manifest schema version is invalid")
counts = payload["critical_row_counts"]
if not isinstance(counts, dict) or set(counts) != set(expected_datasets):
    raise SystemExit("manifest critical row counts are incomplete")
if any(
    not isinstance(counts[name], int)
    or isinstance(counts[name], bool)
    or counts[name] <= 0
    for name in expected_datasets
):
    raise SystemExit("manifest critical row count is invalid")
print(schema_version)
print(created_at)
for name in expected_datasets:
    print(f"{name}\t{counts[name]}")
PY
) || fail invalid_dump_manifest "the dump manifest could not be validated"
mapfile -t manifest_lines <<<"$manifest_output"
[[ ${#manifest_lines[@]} -eq 6 && ${manifest_lines[0]} =~ ^[0-9]+$ ]] \
	|| fail invalid_dump_manifest "the dump manifest output was incomplete"
source_schema_version=${manifest_lines[0]}
dump_created_at=${manifest_lines[1]}
declare -A manifest_counts=()
for manifest_line in "${manifest_lines[@]:2}"; do
	IFS=$'\t' read -r manifest_dataset manifest_count <<<"$manifest_line"
	[[ -n $manifest_dataset && $manifest_count =~ ^[0-9]+$ ]] \
		|| fail invalid_dump_manifest "the dump manifest count was invalid"
	manifest_counts["$manifest_dataset"]=$manifest_count
done

dump_name=$selected_name
dump_bytes=$selected_bytes
dump_sha256=$selected_sha256
log "selected $dump_name ($dump_bytes bytes)"

drop_and_verify_scratch \
	|| fail scratch_precleanup_failed "an existing scratch database could not be removed"

# Measured after the pre-cleanup, so a leftover scratch database's bytes count as free, and
# before createdb, so a refusal leaves nothing for finish's cleanup to fail to remove.
scratch_data_directory=$(psql_value postgres "SHOW data_directory;") \
	|| fail insufficient_free_space "the scratch cluster data directory could not be read"
scratch_data_directory=${scratch_data_directory//[[:space:]]/}
source_database_bytes=$(psql_value postgres "SELECT pg_database_size('$SOURCE');") \
	|| fail insufficient_free_space "the source database size could not be read"
source_database_bytes=${source_database_bytes//[[:space:]]/}
available_bytes=$(df --block-size=1 --output=avail -- "$scratch_data_directory" | tail -n 1) \
	|| fail insufficient_free_space "free space on the scratch filesystem could not be read"
available_bytes=${available_bytes//[[:space:]]/}
[[ -n $scratch_data_directory && $source_database_bytes =~ ^[0-9]+$ && $available_bytes =~ ^[0-9]+$ ]] \
	|| fail insufficient_free_space "the free-space precheck could not be measured"
# pg_database_size bounds the restored copy; the 10 GiB margin is a guess, for the WAL written
# between checkpoints and pg_restore's sort temp files. spec-data-platform.md 3.2(a) argues it.
required_bytes=$((source_database_bytes + 10737418240))
(( available_bytes >= required_bytes )) \
	|| fail insufficient_free_space \
		"$scratch_data_directory has $available_bytes bytes free; the restore needs $required_bytes"
log "free space: $available_bytes bytes on $scratch_data_directory, $required_bytes required"

runuser -u postgres -- createdb --owner=glasswell "$SCRATCH" \
	|| fail scratch_create_failed "the scratch database could not be created"

log "restoring the selected dump into the scratch database"
runuser -u postgres -- pg_restore --exit-on-error --dbname "$SCRATCH" "$newest" \
	|| fail restore_failed "pg_restore failed"

postgis_version=$(psql_value "$SCRATCH" "SELECT postgis_version();") \
	|| fail postgis_assertion_failed "the PostGIS read failed"
[[ -n ${postgis_version//[[:space:]]/} ]] \
	|| fail postgis_assertion_failed "the PostGIS read was empty"
append_read_assertion postgis_available true

extension_present=$(psql_value "$SCRATCH" \
	"SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'postgis');") \
	|| fail extension_assertion_failed "the extension read failed"
[[ ${extension_present//[[:space:]]/} == t ]] \
	|| fail extension_assertion_failed "the PostGIS extension is absent"
append_read_assertion postgis_extension true

scratch_owner=$(psql_value postgres \
	"SELECT pg_catalog.pg_get_userbyid(datdba) FROM pg_database WHERE datname = '$SCRATCH';") \
	|| fail owner_assertion_failed "the scratch owner read failed"
[[ ${scratch_owner//[[:space:]]/} == glasswell ]] \
	|| fail owner_assertion_failed "the scratch database owner is incorrect"
append_read_assertion scratch_owner true

restored_schema_version=$(psql_value "$SCRATCH" \
	"SELECT coalesce(max(version), 0) FROM public.schema_migrations;") \
	|| fail schema_head_query_failed "the restored schema head could not be read"
restored_schema_version=${restored_schema_version//[[:space:]]/}
[[ $source_schema_version =~ ^[0-9]+$ && $restored_schema_version =~ ^[0-9]+$ ]] \
	|| fail schema_head_query_failed "a schema head was invalid"
[[ $source_schema_version == "$restored_schema_version" ]] \
	|| fail schema_head_mismatch "the restored schema head differs from its dump manifest"

critical_datasets=(
	lineage.manifests
	canonical.wells_latest
	canonical.production_monthly
	marts.nd_wells_tile
)
for dataset in "${critical_datasets[@]}"; do
	source_rows=${manifest_counts[$dataset]:-}
	restored_rows=$(psql_value "$SCRATCH" "SELECT count(*) FROM $dataset;") \
		|| fail critical_count_query_failed "a restored critical row count failed"
	restored_rows=${restored_rows//[[:space:]]/}
	[[ $source_rows =~ ^[0-9]+$ && $restored_rows =~ ^[0-9]+$ ]] \
		|| fail critical_count_query_failed "a critical row count was invalid"
	append_row_comparison "$dataset" "$source_rows" "$restored_rows"
	(( source_rows > 0 && restored_rows > 0 )) \
		|| fail critical_dataset_empty "a production critical dataset is empty"
	[[ $source_rows == "$restored_rows" ]] \
		|| fail critical_count_mismatch "a restored critical row count differs from its dump manifest"
done

representative_queries=(
	"canonical_well|SELECT EXISTS (SELECT 1 FROM canonical.wells_latest WHERE api10 IS NOT NULL);"
	"production_observation|SELECT EXISTS (SELECT 1 FROM canonical.production_monthly WHERE production_month IS NOT NULL AND stream IN ('oil','gas','water'));"
	"lineage_manifest|SELECT EXISTS (SELECT 1 FROM lineage.manifests WHERE manifest_id IS NOT NULL AND sha256 IS NOT NULL);"
)
for assertion in "${representative_queries[@]}"; do
	assertion_id=${assertion%%|*}
	statement=${assertion#*|}
	assertion_value=$(psql_value "$SCRATCH" "$statement") \
		|| fail representative_read_failed "a representative restored read failed"
	if [[ ${assertion_value//[[:space:]]/} != t ]]; then
		append_read_assertion "$assertion_id" false
		fail representative_read_failed "a representative restored read returned no row"
	fi
	append_read_assertion "$assertion_id" true
done

result=passed
failure_detail=""
