"""The replacement-host recovery procedure, exercised against stubs.

The real procedure has never been run: it needs a second VM, forge headroom and a read-capable
off-box grant, none of which exist. These tests hold its command sequence, its refusals and its
receipt shape so the one eventual execution is a rehearsal rather than a first draft.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from glasswell.status.models import RecoveryDrillResult

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
RECOVERY = ROOT / "infra" / "backup" / "glasswell-recovery-drill.sh"
DURABLE_WRITE = ROOT / "infra" / "backup" / "glasswell-durable-write.py"

GENERATION = "20260830T020825Z"
SCHEMA_HEAD = "54"
COUNTS = {
    "lineage.manifests": 197,
    "canonical.wells_latest": 403238,
    "canonical.production_monthly": 7223544,
    "marts.nd_wells_tile": 43817,
}

STUBS = {
    "install": '#!/bin/bash\nfor last; do :; done\nmkdir -p "$last"\n',
    "runuser": '#!/bin/bash\nshift 2; [ "$1" = -- ] && shift\nexec "$@"\n',
    "createdb": '#!/bin/bash\nprintf "createdb %s\\n" "$*" >> "$STUB_LOG"\n',
    "pg_restore": '#!/bin/bash\nprintf "pg_restore %s\\n" "$*" >> "$STUB_LOG"\n',
    # Materialises the generation the pull is supposed to bring back, manifest included, so the
    # script's manifest-versus-archive identity check runs against real bytes and a real hash.
    "rsync": r'''#!/bin/bash
printf 'rsync %s\n' "$*" >> "$STUB_LOG"
[ -n "${RSYNC_FAIL:-}" ] && exit 23
stream=""
for arg; do
  case "$arg" in
    */pgdump/) stream=pgdump ;;
    */raw/) stream=raw ;;
  esac
done
for last; do :; done
mkdir -p "$last"
if [ "$stream" = pgdump ]; then
  dump="$last/glasswell-$STUB_GENERATION.dump"
  printf archive > "$dump"
  printf 'CREATE ROLE glasswell;\n' > "$last/globals-$STUB_GENERATION.sql"
  sha=$(sha256sum "$dump" | cut -d' ' -f1)
  bytes=$(stat -c %s "$dump")
  cat > "$last/glasswell-$STUB_GENERATION.manifest.json" <<JSON
{"manifest_version":1, "database":"glasswell", "created_at":"2026-08-30T02:08:25Z",
 "dump":{"name":"glasswell-$STUB_GENERATION.dump","sha256":"$sha","bytes":$bytes},
 "source_schema_version":$STUB_MANIFEST_SCHEMA,
 "critical_row_counts":{"lineage.manifests":197,"canonical.wells_latest":403238,
                        "canonical.production_monthly":7223544,"marts.nd_wells_tile":43817}}
JSON
else
  printf 'raw-bytes' > "$last/sample.csv"
fi
''',
    "psql": r'''#!/bin/bash
statement=""
while [ $# -gt 0 ]; do
  case "$1" in
    --command) statement="$2"; shift 2 ;;
    --file) printf 'psql --file %s\n' "$2" >> "$STUB_LOG"; exit 0 ;;
    *) shift ;;
  esac
done
printf 'psql %s\n' "$statement" >> "$STUB_LOG"
case "$statement" in
  *schema_migrations*) printf '%s\n' "$STUB_RESTORED_SCHEMA" ;;
  *"FROM lineage.manifests;"*) printf '%s\n' "$STUB_MANIFEST_ROWS" ;;
  *"FROM canonical.wells_latest;"*) printf '403238\n' ;;
  *"FROM canonical.production_monthly;"*) printf '7223544\n' ;;
  *"FROM marts.nd_wells_tile;"*) printf '43817\n' ;;
  *EXISTS*) printf 't\n' ;;
esac
''',
}


def write_stubs(binaries: Path) -> None:
    binaries.mkdir(parents=True, exist_ok=True)
    for name, body in STUBS.items():
        path = binaries / name
        path.write_text(body, encoding="utf-8")
        path.chmod(0o755)


def receipt_path(tmp_path: Path) -> Path:
    return tmp_path / "recovery-state" / "result.json"


def run_recovery(tmp_path: Path, **extra: str) -> subprocess.CompletedProcess[str]:
    binaries = tmp_path / "bin"
    write_stubs(binaries)
    return subprocess.run(
        ["/bin/bash", str(RECOVERY)],
        capture_output=True,
        text=True,
        check=False,
        env={
            **os.environ,
            "PATH": f"{binaries}:{os.environ['PATH']}",
            "STUB_LOG": str(tmp_path / "commands.log"),
            "STUB_GENERATION": GENERATION,
            "STUB_RESTORED_SCHEMA": SCHEMA_HEAD,
            "STUB_MANIFEST_SCHEMA": SCHEMA_HEAD,
            "STUB_MANIFEST_ROWS": str(COUNTS["lineage.manifests"]),
            "RECOVERY_SOURCE": "root@forge:/hdd-pool/backups/glasswell",
            "RECOVERY_WORK_DIR": str(tmp_path / "work"),
            "RECOVERY_RAW_DIR": str(tmp_path / "raw"),
            "RECOVERY_DATABASE": "glasswell_recovery",
            "RECOVERY_RESULT_PATH": str(receipt_path(tmp_path)),
            "RECOVERY_RESULT_UID": str(os.getuid()),
            "RECOVERY_RESULT_GID": str(os.getgid()),
            "DURABLE_WRITE": str(DURABLE_WRITE),
            **extra,
        },
    )


def read_receipt(tmp_path: Path) -> dict:
    return json.loads(receipt_path(tmp_path).read_text(encoding="utf-8"))


def test_recovery_restores_globals_then_the_dump_then_the_raw_zone(tmp_path: Path) -> None:
    completed = run_recovery(tmp_path)
    assert completed.returncode == 0, completed.stdout + completed.stderr

    commands = (tmp_path / "commands.log").read_text(encoding="utf-8")
    globals_call = commands.index("psql --file")
    create = commands.index("createdb")
    restore = commands.index("pg_restore")
    raw_pull = commands.index("/raw/")
    # A fresh cluster has none of the roles the dump's objects are owned by.
    assert globals_call < create < restore
    # The raw zone is the half that cannot be rebuilt from the database, so it is not optional.
    assert restore < raw_pull
    assert "--owner=glasswell glasswell_recovery" in commands


def test_recovery_publishes_a_receipt_the_status_collector_accepts(tmp_path: Path) -> None:
    run_recovery(tmp_path)
    receipt = RecoveryDrillResult.model_validate_json(
        receipt_path(tmp_path).read_text(encoding="utf-8")
    )
    assert receipt.result == "passed"
    assert receipt.schema_match is True
    assert receipt.restored_schema_version == int(SCHEMA_HEAD)
    assert receipt.globals_restored is True
    assert receipt.target_database == "glasswell_recovery"
    assert receipt.raw_zone.files == 1
    assert {item.dataset: item.source_rows for item in receipt.critical_row_counts} == COUNTS
    assert all(item.passed for item in receipt.representative_reads)


def test_recovery_refuses_the_production_database(tmp_path: Path) -> None:
    """Restoring a backup over the live database is the one outcome that is worse than no drill."""
    completed = run_recovery(tmp_path, RECOVERY_DATABASE="glasswell")
    assert completed.returncode != 0
    assert read_receipt(tmp_path)["failure_detail"] == "refuses_production_database"
    # The refusal lands before the first stub runs, so nothing was even pulled.
    assert not (tmp_path / "commands.log").exists()


def test_recovery_refuses_without_a_read_capable_source(tmp_path: Path) -> None:
    completed = run_recovery(tmp_path, RECOVERY_SOURCE="")
    assert completed.returncode != 0
    assert read_receipt(tmp_path)["failure_detail"] == "no_recovery_source"


def test_recovery_refuses_a_dump_its_manifest_does_not_identify(tmp_path: Path) -> None:
    binaries = tmp_path / "bin"
    write_stubs(binaries)
    tampered = (binaries / "rsync").read_text(encoding="utf-8").replace(
        'printf archive > "$dump"', 'printf tampered > "$dump"'
    ).replace('sha=$(sha256sum "$dump" | cut -d\' \' -f1)', 'sha=$(printf "%064d" 0)')
    (binaries / "rsync").write_text(tampered, encoding="utf-8")
    (binaries / "rsync").chmod(0o755)

    completed = subprocess.run(
        ["/bin/bash", str(RECOVERY)],
        capture_output=True,
        text=True,
        check=False,
        env={
            **os.environ,
            "PATH": f"{binaries}:{os.environ['PATH']}",
            "STUB_LOG": str(tmp_path / "commands.log"),
            "STUB_GENERATION": GENERATION,
            "STUB_RESTORED_SCHEMA": SCHEMA_HEAD,
            "STUB_MANIFEST_SCHEMA": SCHEMA_HEAD,
            "STUB_MANIFEST_ROWS": str(COUNTS["lineage.manifests"]),
            "RECOVERY_SOURCE": "root@forge:/hdd-pool/backups/glasswell",
            "RECOVERY_WORK_DIR": str(tmp_path / "work"),
            "RECOVERY_RAW_DIR": str(tmp_path / "raw"),
            "RECOVERY_RESULT_PATH": str(receipt_path(tmp_path)),
            "RECOVERY_RESULT_UID": str(os.getuid()),
            "RECOVERY_RESULT_GID": str(os.getgid()),
            "DURABLE_WRITE": str(DURABLE_WRITE),
        },
    )
    assert completed.returncode != 0
    assert read_receipt(tmp_path)["failure_detail"] == "invalid_dump_manifest"


def test_recovery_refuses_a_restored_schema_head_below_its_manifest(tmp_path: Path) -> None:
    completed = run_recovery(tmp_path, STUB_RESTORED_SCHEMA="53")
    assert completed.returncode != 0
    receipt = read_receipt(tmp_path)
    assert receipt["failure_detail"] == "schema_head_mismatch"
    assert receipt["schema_match"] is False


def test_recovery_refuses_a_critical_row_count_that_disagrees(tmp_path: Path) -> None:
    completed = run_recovery(tmp_path, STUB_MANIFEST_ROWS="196")
    assert completed.returncode != 0
    receipt = read_receipt(tmp_path)
    assert receipt["failure_detail"] == "critical_count_mismatch"
    comparison = next(
        item for item in receipt["critical_row_counts"] if item["dataset"] == "lineage.manifests"
    )
    assert comparison["match"] is False


def test_recovery_records_a_failed_off_box_pull(tmp_path: Path) -> None:
    completed = run_recovery(tmp_path, RSYNC_FAIL="1")
    assert completed.returncode != 0
    assert read_receipt(tmp_path)["failure_detail"] == "offsite_pull_failed"


def test_a_failed_recovery_receipt_is_never_a_passed_one(tmp_path: Path) -> None:
    """The model must refuse a receipt that claims success without the evidence for it."""
    run_recovery(tmp_path, STUB_RESTORED_SCHEMA="53")
    payload = read_receipt(tmp_path)
    payload["result"] = "passed"
    payload["failure_detail"] = None
    with pytest.raises(ValueError, match="matching schema head"):
        RecoveryDrillResult.model_validate(payload)
