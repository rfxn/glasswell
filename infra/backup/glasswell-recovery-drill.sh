#!/bin/bash
# Rebuild glasswell on a replacement host from the off-box copy: globals, the logical dump and
# the raw zone, then prove the restored database answers. Publishes a durable receipt.
#
# THIS PROCEDURE HAS NEVER BEEN EXECUTED END TO END. It is mechanised and unit-tested against
# stubs; no run against a real replacement VM has happened. See infra/README.md.
set -uo pipefail

RECOVERY_SOURCE="${RECOVERY_SOURCE:-}"
RECOVERY_WORK_DIR="${RECOVERY_WORK_DIR:-/data/scratch/recovery}"
RECOVERY_RAW_DIR="${RECOVERY_RAW_DIR:-/data/raw}"
RECOVERY_DATABASE="${RECOVERY_DATABASE:-glasswell_recovery}"
RECOVERY_OWNER="${RECOVERY_OWNER:-glasswell}"
RECOVERY_SSH_KEY="${RECOVERY_SSH_KEY:-/root/.ssh/id_glasswell_recovery}"
RESULT_PATH="${RECOVERY_RESULT_PATH:-/var/lib/glasswell-recovery-drill/result.json}"
RESULT_UID="${RECOVERY_RESULT_UID:-root}"
RESULT_GID="${RECOVERY_RESULT_GID:-glasswell}"
DURABLE_WRITE="${DURABLE_WRITE:-/usr/local/sbin/glasswell-durable-write.py}"
PRODUCTION_DATABASE=glasswell

started_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
started_epoch=$(date -u +%s)
result=failed
failure_detail=recovery_interrupted
dump_name=""
dump_sha256=""
dump_bytes=""
source_schema_version=""
restored_schema_version=""
row_comparisons=""
read_assertions=""
globals_restored=false
raw_files=""
raw_bytes=""

log() { printf '%s\n' "$*"; }

fail() {
	failure_detail=$1
	log "FAIL: $2"
	exit 1
}

psql_value() {
	local database=$1 statement=$2
	runuser -u postgres -- psql --no-psqlrc --set=ON_ERROR_STOP=1 \
		--tuples-only --no-align --dbname "$database" --command "$statement"
}

append_row_comparison() {
	printf -v row_comparisons '%s%s\t%s\t%s\n' "$row_comparisons" "$1" "$2" "$3"
}

append_read_assertion() {
	printf -v read_assertions '%s%s\t%s\n' "$read_assertions" "$1" "$2"
}

write_result() {
	RECOVERY_RESULT="$result" \
	RECOVERY_FAILURE_DETAIL="$failure_detail" \
	RECOVERY_DUMP_NAME="$dump_name" \
	RECOVERY_DUMP_SHA256="$dump_sha256" \
	RECOVERY_DUMP_BYTES="$dump_bytes" \
	RECOVERY_SOURCE_SCHEMA="$source_schema_version" \
	RECOVERY_RESTORED_SCHEMA="$restored_schema_version" \
	RECOVERY_STARTED_AT="$started_at" \
	RECOVERY_COMPLETED_AT="$1" \
	RECOVERY_DURATION_SECONDS="$2" \
	RECOVERY_ROW_COMPARISONS="$row_comparisons" \
	RECOVERY_READ_ASSERTIONS="$read_assertions" \
	RECOVERY_GLOBALS_RESTORED="$globals_restored" \
	RECOVERY_RAW_FILES="$raw_files" \
	RECOVERY_RAW_BYTES="$raw_bytes" \
	RECOVERY_TARGET_DATABASE="$RECOVERY_DATABASE" \
	/usr/bin/python3 - <<'PY' | /usr/bin/python3 "$DURABLE_WRITE" "$RESULT_PATH" "$RESULT_UID" "$RESULT_GID"
import json
import os
import re


def optional_integer(name):
    value = os.environ[name]
    if not value:
        return None
    if not value.isdecimal():
        raise SystemExit(f"invalid {name}")
    return int(value)


dump_name = os.environ["RECOVERY_DUMP_NAME"] or None
dump_sha256 = os.environ["RECOVERY_DUMP_SHA256"] or None
if dump_name is not None and not re.fullmatch(r"glasswell-\d{8}T\d{6}Z\.dump", dump_name):
    raise SystemExit("invalid dump name")
if dump_sha256 is not None and not re.fullmatch(r"[0-9a-f]{64}", dump_sha256):
    raise SystemExit("invalid dump hash")

row_comparisons = []
for line in os.environ["RECOVERY_ROW_COMPARISONS"].splitlines():
    dataset, source_rows, restored_rows = line.split("\t")
    row_comparisons.append(
        {
            "dataset": dataset,
            "source_rows": int(source_rows),
            "restored_rows": int(restored_rows),
            "match": source_rows == restored_rows,
        }
    )

read_assertions = []
for line in os.environ["RECOVERY_READ_ASSERTIONS"].splitlines():
    assertion_id, passed = line.split("\t")
    read_assertions.append({"id": assertion_id, "passed": passed == "true"})

result = os.environ["RECOVERY_RESULT"]
failure_detail = os.environ["RECOVERY_FAILURE_DETAIL"] or None
if result not in {"passed", "failed"}:
    raise SystemExit("invalid recovery result")
if (result == "passed") != (failure_detail is None):
    raise SystemExit("inconsistent recovery result")

source_schema = optional_integer("RECOVERY_SOURCE_SCHEMA")
restored_schema = optional_integer("RECOVERY_RESTORED_SCHEMA")
print(
    json.dumps(
        {
            "receipt_version": 1,
            "result": result,
            "failure_detail": failure_detail,
            "target_database": os.environ["RECOVERY_TARGET_DATABASE"],
            "dump": (
                None
                if dump_name is None
                else {
                    "name": dump_name,
                    "sha256": dump_sha256,
                    "bytes": optional_integer("RECOVERY_DUMP_BYTES"),
                }
            ),
            "started_at": os.environ["RECOVERY_STARTED_AT"],
            "completed_at": os.environ["RECOVERY_COMPLETED_AT"],
            "duration_seconds": optional_integer("RECOVERY_DURATION_SECONDS"),
            "source_schema_version": source_schema,
            "restored_schema_version": restored_schema,
            "schema_match": (
                source_schema == restored_schema
                if source_schema is not None and restored_schema is not None
                else None
            ),
            "critical_row_counts": row_comparisons,
            "representative_reads": read_assertions,
            "globals_restored": os.environ["RECOVERY_GLOBALS_RESTORED"] == "true",
            "raw_zone": {
                "files": optional_integer("RECOVERY_RAW_FILES"),
                "bytes": optional_integer("RECOVERY_RAW_BYTES"),
            },
        }
    )
)
PY
}

finish() {
	local exit_code=$? completed_at duration_seconds
	trap - EXIT HUP INT TERM
	if [[ $exit_code -ne 0 ]]; then
		result=failed
	elif [[ $result != passed ]]; then
		result=failed
		failure_detail=recovery_interrupted
		exit_code=1
	fi
	completed_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
	duration_seconds=$(( $(date -u +%s) - started_epoch ))
	if ! write_result "$completed_at" "$duration_seconds"; then
		log "FAIL: durable recovery result could not be written"
		exit_code=1
	fi
	[[ $exit_code -eq 0 ]] && log "OK: recovery drill passed; durable proof recorded"
	exit "$exit_code"
}

trap finish EXIT
trap 'failure_detail=recovery_interrupted; exit 129' HUP
trap 'failure_detail=recovery_interrupted; exit 130' INT
trap 'failure_detail=recovery_interrupted; exit 143' TERM

install -d -m 0750 -o "$RESULT_UID" -g "$RESULT_GID" "$(dirname "$RESULT_PATH")" \
	|| fail result_dir_unavailable "the recovery receipt directory could not be created"

# A recovery drill restores a whole cluster's worth of roles and data. Pointing it at the live
# database would overwrite production with a backup, which is the one thing it must never do.
# The name reaches `psql --command`, so treat it as hostile: compare case-folded (postgres folds
# unquoted identifiers itself) and allow only a plain identifier, which also makes the quoted
# interpolation below unable to carry a statement separator.
# Both comparisons pin LC_ALL=C: under en_US.UTF-8 glibc collation `[a-z]` also matches
# fullwidth forms such as U+FF47, and `tr` ranges are locale-sensitive the same way. Pinned
# rather than reasoned about, because the locale this runs under on a replacement host is not
# something the script gets to know.
normalised_database=$(printf '%s' "$RECOVERY_DATABASE" | LC_ALL=C tr '[:upper:]' '[:lower:]')
[[ $normalised_database != "$PRODUCTION_DATABASE" ]] \
	|| fail refuses_production_database "the recovery target is the production database"
( LC_ALL=C; [[ $RECOVERY_DATABASE =~ ^[a-z][a-z0-9_]{0,62}$ ]] ) \
	|| fail unsafe_target_database "the recovery target is not a plain lowercase identifier"
[[ -n $RECOVERY_SOURCE ]] \
	|| fail no_recovery_source "RECOVERY_SOURCE is unset; it needs a read-capable off-box path"

# The globals restore rewrites cluster roles and the raw-zone pull writes $RECOVERY_RAW_DIR,
# which defaults to the production raw zone. Neither is stopped by the target-name refusal
# above, so the host itself is refused: a replacement host has no production database and is
# not yet serving. `install.sh` places this script on VM 111, so this guard is what stands
# between a stray invocation there and the irreplaceable half of the system.
# Fails closed: a probe that cannot answer is treated as "this might be production".
production_databases=$(psql_value postgres \
	"SELECT count(*) FROM pg_database WHERE datname = '$PRODUCTION_DATABASE';") \
	|| fail production_probe_failed "could not determine whether this is the production host"
[[ ${production_databases//[[:space:]]/} == 0 ]] \
	|| fail refuses_production_host "the production database exists in this cluster"
[[ $(systemctl is-active glasswell-api.service) != active ]] \
	|| fail refuses_production_host "glasswell-api is active, so this is not a replacement host"

mkdir -p "$RECOVERY_WORK_DIR" || fail work_dir_unavailable "cannot create $RECOVERY_WORK_DIR"

# The production push uses `rrsync -wo` on forge, which cannot serve a read. This pull therefore
# needs a separate read-capable grant that does not exist yet — see infra/README.md.
log "pulling the off-box backup generation from $RECOVERY_SOURCE"
rsync -aH -e "ssh -i $RECOVERY_SSH_KEY -o BatchMode=yes -o IdentitiesOnly=yes -o ConnectTimeout=15" \
	"$RECOVERY_SOURCE/pgdump/" "$RECOVERY_WORK_DIR/" </dev/null \
	|| fail offsite_pull_failed "the off-box pgdump copy could not be pulled"

newest=""
selected_manifest=""
newest_timestamp=0
shopt -s nullglob
for candidate_manifest in "$RECOVERY_WORK_DIR"/glasswell-*.manifest.json; do
	manifest_name=${candidate_manifest##*/}
	[[ $manifest_name =~ ^glasswell-[0-9]{8}T[0-9]{6}Z\.manifest\.json$ ]] \
		|| fail unsafe_dump_manifest "a pulled manifest has an invalid name"
	manifest_timestamp=$(stat -c %Y -- "$candidate_manifest") \
		|| fail dump_stat_failed "a pulled manifest could not be stat'd"
	candidate=${candidate_manifest%.manifest.json}.dump
	[[ -f $candidate && ! -L $candidate ]] \
		|| fail manifest_dump_missing "a pulled manifest has no archive"
	if (( manifest_timestamp > newest_timestamp )); then
		newest_timestamp=$manifest_timestamp
		newest=$candidate
		selected_manifest=$candidate_manifest
	fi
done
shopt -u nullglob
[[ -n $newest ]] || fail no_dump_found "the off-box copy holds no complete generation"

selected_name=${newest##*/}
generation=${selected_name#glasswell-}
generation=${generation%.dump}
globals_file="$RECOVERY_WORK_DIR/globals-$generation.sql"
[[ -s $globals_file ]] || fail no_globals_dump "the generation has no non-empty globals dump"

selected_bytes=$(stat -c %s -- "$newest") || fail dump_stat_failed "dump size could not be read"
selected_sha256=$(sha256sum -- "$newest") || fail dump_hash_failed "dump hash could not be computed"
selected_sha256=${selected_sha256%% *}

manifest_output=$(/usr/bin/python3 - "$selected_manifest" "$selected_name" "$selected_sha256" \
	"$selected_bytes" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
dump = payload["dump"]
if dump != {"name": sys.argv[2], "sha256": sys.argv[3], "bytes": int(sys.argv[4])}:
    raise SystemExit("the manifest does not identify the pulled archive")
schema_version = payload["source_schema_version"]
if not isinstance(schema_version, int) or isinstance(schema_version, bool) or schema_version < 0:
    raise SystemExit("manifest schema version is invalid")
counts = payload["critical_row_counts"]
print(schema_version)
for name in (
    "lineage.manifests",
    "canonical.wells_latest",
    "canonical.production_monthly",
    "marts.nd_wells_tile",
):
    print(f"{name}\t{counts[name]}")
PY
) || fail invalid_dump_manifest "the pulled manifest could not be validated against its archive"

mapfile -t manifest_lines <<<"$manifest_output"
[[ ${#manifest_lines[@]} -eq 5 ]] \
	|| fail invalid_dump_manifest "the pulled manifest output was incomplete"
source_schema_version=${manifest_lines[0]}
declare -A manifest_counts=()
for manifest_line in "${manifest_lines[@]:1}"; do
	IFS=$'\t' read -r manifest_dataset manifest_count <<<"$manifest_line"
	manifest_counts["$manifest_dataset"]=$manifest_count
done

dump_name=$selected_name
dump_bytes=$selected_bytes
dump_sha256=$selected_sha256
log "recovering generation $generation ($dump_bytes bytes)"

# Globals first: the dump's objects are owned by roles that do not exist on a fresh cluster.
runuser -u postgres -- psql --no-psqlrc --set=ON_ERROR_STOP=1 --dbname postgres \
	--file "$globals_file" \
	|| fail globals_restore_failed "the cluster globals could not be restored"
globals_restored=true

psql_value postgres "DROP DATABASE IF EXISTS \"$RECOVERY_DATABASE\" WITH (FORCE);" >/dev/null \
	|| fail target_precleanup_failed "an existing recovery database could not be removed"
runuser -u postgres -- createdb --owner="$RECOVERY_OWNER" "$RECOVERY_DATABASE" \
	|| fail target_create_failed "the recovery database could not be created"
runuser -u postgres -- pg_restore --exit-on-error --dbname "$RECOVERY_DATABASE" "$newest" \
	|| fail restore_failed "pg_restore failed against the recovery database"

restored_schema_version=$(psql_value "$RECOVERY_DATABASE" \
	"SELECT coalesce(max(version), 0) FROM public.schema_migrations;") \
	|| fail schema_head_query_failed "the restored schema head could not be read"
restored_schema_version=${restored_schema_version//[[:space:]]/}
[[ $source_schema_version == "$restored_schema_version" ]] \
	|| fail schema_head_mismatch "the restored schema head differs from its manifest"

for dataset in lineage.manifests canonical.wells_latest canonical.production_monthly \
               marts.nd_wells_tile; do
	source_rows=${manifest_counts[$dataset]:-}
	restored_rows=$(psql_value "$RECOVERY_DATABASE" "SELECT count(*) FROM $dataset;") \
		|| fail critical_count_query_failed "a restored critical row count failed"
	restored_rows=${restored_rows//[[:space:]]/}
	append_row_comparison "$dataset" "$source_rows" "$restored_rows"
	[[ $source_rows == "$restored_rows" ]] \
		|| fail critical_count_mismatch "a restored critical row count differs from its manifest"
done

for assertion in \
	"postgis_extension|SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'postgis');" \
	"canonical_well|SELECT EXISTS (SELECT 1 FROM canonical.wells_latest WHERE api10 IS NOT NULL);" \
	"production_observation|SELECT EXISTS (SELECT 1 FROM canonical.production_monthly WHERE production_month IS NOT NULL);" \
	"lineage_manifest|SELECT EXISTS (SELECT 1 FROM lineage.manifests WHERE manifest_id IS NOT NULL);"; do
	assertion_id=${assertion%%|*}
	assertion_value=$(psql_value "$RECOVERY_DATABASE" "${assertion#*|}") \
		|| fail representative_read_failed "a representative restored read failed"
	if [[ ${assertion_value//[[:space:]]/} != t ]]; then
		append_read_assertion "$assertion_id" false
		fail representative_read_failed "a representative restored read returned no row"
	fi
	append_read_assertion "$assertion_id" true
done

# The raw zone is the irreplaceable half: the database can be rebuilt from it, not the reverse.
log "restoring the raw zone into $RECOVERY_RAW_DIR"
mkdir -p "$RECOVERY_RAW_DIR" || fail raw_zone_unavailable "cannot create $RECOVERY_RAW_DIR"
rsync -aH -e "ssh -i $RECOVERY_SSH_KEY -o BatchMode=yes -o IdentitiesOnly=yes -o ConnectTimeout=15" \
	"$RECOVERY_SOURCE/raw/" "$RECOVERY_RAW_DIR/" </dev/null \
	|| fail raw_zone_pull_failed "the off-box raw zone could not be pulled"
raw_files=$(find "$RECOVERY_RAW_DIR" -type f | wc -l) \
	|| fail raw_zone_unavailable "the restored raw zone could not be counted"
raw_files=${raw_files//[[:space:]]/}
raw_bytes=$(du -sb "$RECOVERY_RAW_DIR" | cut -f1) \
	|| fail raw_zone_unavailable "the restored raw zone could not be measured"
(( raw_files > 0 )) || fail raw_zone_empty "the restored raw zone holds no files"

result=passed
failure_detail=""
