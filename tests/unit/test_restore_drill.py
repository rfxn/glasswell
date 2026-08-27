"""Fail-closed restore-drill behavior driven through stubbed PostgreSQL commands."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
DRILL = ROOT / "infra" / "backup" / "glasswell-restore-drill.sh"
SCRATCH = "glasswell_restore_test"

PSQL_STUB = r"""#!/bin/bash
printf 'psql %s\n' "$*" >> "$DRILL_LOG"
database=""
statement=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --dbname) database=$2; shift 2 ;;
    --command) statement=$2; shift 2 ;;
    *) shift ;;
  esac
done
case "$statement" in
  "DROP DATABASE"*) exit "${STUB_DROP_RC:-0}" ;;
  *"count(*) FROM pg_database"*) printf '%s\n' "${STUB_REMAINING:-0}" ;;
  *"postgis_version"*)
    [ "${STUB_POSTGIS_RC:-0}" = 0 ] || exit "$STUB_POSTGIS_RC"
    printf '%s\n' "${STUB_POSTGIS_VALUE:-3.4.0}"
    ;;
  *"FROM pg_extension"*) printf '%s\n' "${STUB_EXTENSION_VALUE:-t}" ;;
  *"pg_get_userbyid"*) printf '%s\n' "${STUB_OWNER_VALUE:-glasswell}" ;;
  *"max(version)"*)
    if [[ "$database" = glasswell_restore_* ]]; then
      printf '%s\n' "${STUB_RESTORED_SCHEMA:-44}"
    else
      printf '%s\n' "${STUB_SOURCE_SCHEMA:-44}"
    fi
    ;;
  *"SELECT count(*) FROM lineage.manifests"*|\
  *"SELECT count(*) FROM canonical.wells_latest"*|\
  *"SELECT count(*) FROM canonical.production_monthly"*|\
  *"SELECT count(*) FROM marts.nd_wells_tile"*)
    if [[ "$database" = glasswell_restore_* ]]; then
      printf '%s\n' "${STUB_RESTORED_ROWS:-42}"
    else
      printf '%s\n' "${STUB_SOURCE_ROWS:-42}"
    fi
    ;;
  *"SELECT EXISTS"*) printf '%s\n' "${STUB_READ_VALUE:-t}" ;;
esac
exit 0
"""

STUBS = {
    "psql": PSQL_STUB,
    "runuser": '#!/bin/bash\nshift 2; [ "$1" = -- ] && shift\nexec "$@"\n',
    "createdb": (
        '#!/bin/bash\nprintf \'createdb %s\\n\' "$*" >> "$DRILL_LOG"\n'
        'exit "${STUB_CREATEDB_RC:-0}"\n'
    ),
    "pg_restore": r"""#!/bin/bash
case " $* " in
  *" -l "*) exit "${STUB_ARCHIVE_RC:-0}" ;;
  *) exit "${STUB_RESTORE_RC:-0}" ;;
esac
""",
}


@pytest.fixture
def drill(tmp_path: Path):
    binaries = tmp_path / "bin"
    binaries.mkdir()
    for name, body in STUBS.items():
        stub = binaries / name
        stub.write_text(body, encoding="utf-8")
        stub.chmod(0o755)
    dumps = tmp_path / "dumps"
    dumps.mkdir()
    dump = dumps / "glasswell-20260827T020000Z.dump"
    dump.write_bytes(b"synthetic custom archive")
    dump.chmod(0o640)
    manifest = dumps / "glasswell-20260827T020000Z.manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "manifest_version": 1,
                "database": "glasswell",
                "created_at": "2026-08-27T02:00:00Z",
                "dump": {
                    "name": dump.name,
                    "sha256": hashlib.sha256(dump.read_bytes()).hexdigest(),
                    "bytes": dump.stat().st_size,
                },
                "source_schema_version": 44,
                "critical_row_counts": {
                    "lineage.manifests": 42,
                    "canonical.wells_latest": 42,
                    "canonical.production_monthly": 42,
                    "marts.nd_wells_tile": 42,
                },
            }
        ),
        encoding="utf-8",
    )
    manifest.chmod(0o640)
    result = tmp_path / "restore-result.json"
    calls = tmp_path / "calls.log"
    calls.write_text("", encoding="utf-8")

    def run(**overrides: str) -> tuple[subprocess.CompletedProcess[str], dict | None, str]:
        environment = {
            **os.environ,
            "PATH": f"{binaries}:{os.environ['PATH']}",
            "PGDUMP_DIR": str(dumps),
            "RESTORE_RESULT_PATH": str(result),
            "RESTORE_RESULT_UID": str(os.getuid()),
            "RESTORE_RESULT_GID": str(os.getgid()),
            "EXPECTED_DUMP_OWNER": "root",
            "EXPECTED_DUMP_GROUP": "root",
            "DRILL_LOG": str(calls),
            "GLASSWELL_OWNER_KEY": "must-not-appear",
            **overrides,
        }
        completed = subprocess.run(
            ["/bin/bash", str(DRILL)],
            capture_output=True,
            text=True,
            env=environment,
            check=False,
        )
        payload = (
            json.loads(result.read_text(encoding="utf-8"))
            if result.is_file() and not result.is_symlink()
            else None
        )
        return completed, payload, calls.read_text(encoding="utf-8")

    run.dumps = dumps  # type: ignore[attr-defined]
    run.manifest = manifest  # type: ignore[attr-defined]
    run.result = result  # type: ignore[attr-defined]
    return run


def drop_calls(calls: str) -> int:
    return sum("DROP DATABASE" in line for line in calls.splitlines())


def test_clean_drill_publishes_complete_private_atomic_proof(drill) -> None:
    completed, payload, calls = drill()

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert payload is not None
    assert payload["result"] == "passed"
    assert payload["failure_detail"] is None
    assert payload["dump"]["name"] == "glasswell-20260827T020000Z.dump"
    assert len(payload["dump"]["sha256"]) == 64
    assert payload["dump"]["bytes"] > 0
    assert payload["source_schema_version"] == payload["restored_schema_version"] == 44
    assert len(payload["critical_row_counts"]) == 4
    assert all(
        item["match"] and item["source_rows"] == 42
        for item in payload["critical_row_counts"]
    )
    assert len(payload["representative_reads"]) == 6
    assert all(item["passed"] for item in payload["representative_reads"])
    assert payload["scratch_removed"] is True
    assert drill.result.stat().st_mode & 0o777 == 0o640  # type: ignore[attr-defined]
    assert not list(drill.result.parent.glob(".restore-result.json.*"))  # type: ignore[attr-defined]
    assert drop_calls(calls) >= 2
    assert "OK: restore drill passed" in completed.stdout
    assert "must-not-appear" not in completed.stdout
    assert "must-not-appear" not in json.dumps(payload)


@pytest.mark.parametrize(
    ("overrides", "failure_detail"),
    [
        ({"STUB_RESTORE_RC": "1"}, "restore_failed"),
        ({"STUB_POSTGIS_RC": "1"}, "postgis_assertion_failed"),
        ({"STUB_EXTENSION_VALUE": "f"}, "extension_assertion_failed"),
        ({"STUB_OWNER_VALUE": "postgres"}, "owner_assertion_failed"),
        ({"STUB_RESTORED_SCHEMA": "43"}, "schema_head_mismatch"),
        ({"STUB_RESTORED_ROWS": "41"}, "critical_count_mismatch"),
        ({"STUB_READ_VALUE": "f"}, "representative_read_failed"),
    ],
)
def test_every_assertion_failure_cleans_up_and_publishes_failure(
    drill, overrides: dict[str, str], failure_detail: str
) -> None:
    completed, payload, calls = drill(**overrides)

    assert completed.returncode != 0
    assert payload is not None
    assert payload["result"] == "failed"
    assert payload["failure_detail"] == failure_detail
    assert payload["scratch_removed"] is True
    assert drop_calls(calls) >= 2
    assert "OK: restore drill passed" not in completed.stdout


@pytest.mark.parametrize("overrides", [{"STUB_DROP_RC": "1"}, {"STUB_REMAINING": "1"}])
def test_cleanup_that_fails_or_leaves_scratch_cannot_fall_through_to_success(
    drill, overrides: dict[str, str]
) -> None:
    completed, payload, _ = drill(**overrides)

    assert completed.returncode != 0
    assert payload is not None
    assert payload["result"] == "failed"
    assert payload["failure_detail"] == "scratch_cleanup_failed"
    assert payload["scratch_removed"] is False
    assert "OK: restore drill passed" not in completed.stdout


def test_commit_manifest_without_dump_records_corruption_and_cleans_up(drill) -> None:
    for dump in drill.dumps.glob("*.dump"):  # type: ignore[attr-defined]
        dump.unlink()

    completed, payload, calls = drill()

    assert completed.returncode != 0
    assert payload["failure_detail"] == "manifest_dump_missing"
    assert payload["dump"] is None
    assert payload["scratch_removed"] is True
    assert drop_calls(calls) == 1


def test_symlink_dump_is_refused_without_following_it(drill, tmp_path: Path) -> None:
    original = next(drill.dumps.glob("*.dump"))  # type: ignore[attr-defined]
    original.rename(tmp_path / "outside.dump")
    original.symlink_to(tmp_path / "outside.dump")

    completed, payload, _ = drill()

    assert completed.returncode != 0
    assert payload["failure_detail"] == "unsafe_dump_candidate"


def test_dump_without_commit_manifest_is_not_a_complete_generation(drill) -> None:
    drill.manifest.unlink()  # type: ignore[attr-defined]

    completed, payload, calls = drill()

    assert completed.returncode != 0
    assert payload["failure_detail"] == "no_dump_found"
    assert payload["scratch_removed"] is True
    assert drop_calls(calls) == 1


def test_manifest_that_does_not_identify_dump_is_rejected(drill) -> None:
    manifest = json.loads(drill.manifest.read_text(encoding="utf-8"))  # type: ignore[attr-defined]
    manifest["dump"]["sha256"] = "0" * 64
    drill.manifest.write_text(json.dumps(manifest), encoding="utf-8")  # type: ignore[attr-defined]

    completed, payload, _ = drill()

    assert completed.returncode != 0
    assert payload["failure_detail"] == "invalid_dump_manifest"


def test_unsafe_result_symlink_is_never_replaced_or_reported_as_success(
    drill, tmp_path: Path
) -> None:
    target = tmp_path / "outside-result"
    target.write_text("sentinel", encoding="utf-8")
    drill.result.symlink_to(target)  # type: ignore[attr-defined]

    completed, payload, _ = drill()

    assert completed.returncode != 0
    assert payload is None
    assert target.read_text(encoding="utf-8") == "sentinel"
    assert "OK: restore drill passed" not in completed.stdout
