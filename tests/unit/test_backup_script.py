"""Backup archives are promoted only with exact-vintage private metadata."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
BACKUP = ROOT / "infra" / "backup" / "glasswell-backup.sh"


def test_backup_uses_one_snapshot_and_promotes_complete_private_artifacts(
    tmp_path: Path,
) -> None:
    binaries = tmp_path / "bin"
    binaries.mkdir()
    command_log = tmp_path / "commands.log"
    stubs = {
        "install": '#!/bin/bash\nfor last; do :; done\nmkdir -p "$last"\n',
        "runuser": '#!/bin/bash\nshift 2; [ "$1" = -- ] && shift\nexec "$@"\n',
        "pg_dump": r'''#!/bin/bash
printf 'pg_dump %s\n' "$*" >> "$STUB_LOG"
printf archive
''',
        "pg_dumpall": r'''#!/bin/bash
printf 'pg_dumpall %s\n' "$*" >> "$STUB_LOG"
printf 'CREATE ROLE glasswell;\n'
''',
        "pg_restore": r'''#!/bin/bash
printf 'pg_restore %s\n' "$*" >> "$STUB_LOG"
grep -q archive "$2"
''',
        "psql": r'''#!/bin/bash
while IFS= read -r line; do
  printf 'psql %s\n' "$line" >> "$STUB_LOG"
  case "$line" in
    *BEGIN*) printf 'BEGIN\n' ;;
    *pg_export_snapshot*) printf '00000003-0000001B-1\nSELECT 1\n' ;;
    *json_build_object*)
      printf '%s\n' \
        '{"source_schema_version":44,"critical_row_counts":{'\
'"lineage.manifests":42,"canonical.wells_latest":43,'\
'"canonical.production_monthly":44,"marts.nd_wells_tile":45}}'
      ;;
    *'\q'*) exit 0 ;;
  esac
done
''',
        "chown": '#!/bin/bash\nprintf "chown %s\\n" "$*" >> "$STUB_LOG"\n',
        "chmod": '#!/bin/bash\nprintf "chmod %s\\n" "$*" >> "$STUB_LOG"\n',
        "rsync": '#!/bin/bash\nprintf "rsync %s\\n" "$*" >> "$STUB_LOG"\n',
        "mv": r'''#!/bin/bash
printf 'mv %s\n' "$*" >> "$STUB_LOG"
exec /bin/mv "$@"
''',
    }
    for name, body in stubs.items():
        path = binaries / name
        path.write_text(body, encoding="utf-8")
        path.chmod(0o755)
    dump_dir = tmp_path / "backups" / "pg"
    environment = {
        **os.environ,
        "PATH": f"{binaries}:{os.environ['PATH']}",
        "PGDUMP_DIR": str(dump_dir),
        "RAW_DIR": str(tmp_path / "missing-raw"),
        "STUB_LOG": str(command_log),
    }

    completed = subprocess.run(
        ["/bin/bash", str(BACKUP)],
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    dumps = list(dump_dir.glob("glasswell-*.dump"))
    manifests = list(dump_dir.glob("glasswell-*.manifest.json"))
    globals_files = list(dump_dir.glob("globals-*.sql"))
    assert len(dumps) == len(manifests) == len(globals_files) == 1
    assert not list(dump_dir.glob("*.partial"))
    assert dumps[0].read_bytes() == b"archive"
    assert globals_files[0].read_text(encoding="utf-8") == "CREATE ROLE glasswell;\n"

    payload = json.loads(manifests[0].read_text(encoding="utf-8"))
    assert payload == {
        "manifest_version": 1,
        "database": "glasswell",
        "created_at": payload["created_at"],
        "dump": {
            "name": dumps[0].name,
            "sha256": hashlib.sha256(b"archive").hexdigest(),
            "bytes": 7,
        },
        "source_schema_version": 44,
        "critical_row_counts": {
            "lineage.manifests": 42,
            "canonical.wells_latest": 43,
            "canonical.production_monthly": 44,
            "marts.nd_wells_tile": 45,
        },
    }

    commands = command_log.read_text(encoding="utf-8")
    assert "pg_dump -Fc -Z6 --snapshot=00000003-0000001B-1 -d glasswell" in commands
    assert commands.index("pg_export_snapshot") < commands.index("json_build_object")
    assert commands.index("json_build_object") < commands.index("psql COMMIT;")
    for artifact in (dumps[0], manifests[0], globals_files[0]):
        partial = f"{artifact}.partial"
        assert f"chown root:postgres {partial}" in commands
        assert f"chmod 640 {partial}" in commands
    assert "pg_dumpall --globals-only" in commands
    assert "rsync -aH --delete" in commands
    assert commands.index(f"mv {globals_files[0]}.partial") < commands.index(
        f"mv {dumps[0]}.partial"
    )
    assert commands.index(f"mv {dumps[0]}.partial") < commands.index(
        f"mv {manifests[0]}.partial"
    )
    assert "OK: backup complete" in completed.stdout


def test_backup_refuses_a_concurrent_invocation_before_dumping(tmp_path: Path) -> None:
    binaries = tmp_path / "bin"
    binaries.mkdir()
    install = binaries / "install"
    install.write_text('#!/bin/bash\nfor last; do :; done\nmkdir -p "$last"\n', encoding="utf-8")
    install.chmod(0o755)
    dump_dir = tmp_path / "backups" / "pg"
    dump_dir.mkdir(parents=True)
    lock_path = dump_dir / ".glasswell-backup.lock"
    with lock_path.open("w", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        completed = subprocess.run(
            ["/bin/bash", str(BACKUP)],
            capture_output=True,
            text=True,
            env={
                **os.environ,
                "PATH": f"{binaries}:{os.environ['PATH']}",
                "PGDUMP_DIR": str(dump_dir),
                "RAW_DIR": str(tmp_path / "missing-raw"),
            },
            check=False,
        )

    assert completed.returncode != 0
    assert "FAIL: another backup invocation is active" in completed.stdout
    assert not list(dump_dir.glob("glasswell-*.dump"))
    assert not list(dump_dir.glob("glasswell-*.manifest.json"))


@pytest.mark.parametrize(("failing_command", "message"), [("chown", "chown"), ("chmod", "chmod")])
def test_dump_is_not_promoted_when_private_metadata_step_fails(
    tmp_path: Path, failing_command: str, message: str
) -> None:
    binaries = tmp_path / "bin"
    binaries.mkdir()
    stubs = {
        "install": '#!/bin/bash\nfor last; do :; done\nmkdir -p "$last"\n',
        "runuser": '#!/bin/bash\nshift 2; [ "$1" = -- ] && shift\nexec "$@"\n',
        "pg_dump": '#!/bin/bash\nprintf archive\n',
        "pg_restore": "#!/bin/bash\nexit 0\n",
        "psql": r'''#!/bin/bash
while IFS= read -r line; do
  case "$line" in
    *BEGIN*) printf 'BEGIN\n' ;;
    *pg_export_snapshot*) printf '00000003-0000001B-1\nSELECT 1\n' ;;
    *json_build_object*)
      printf '%s\n' \
        '{"source_schema_version":44,"critical_row_counts":{'\
'"lineage.manifests":42,"canonical.wells_latest":42,'\
'"canonical.production_monthly":42,"marts.nd_wells_tile":42}}'
      ;;
    *'\q'*) exit 0 ;;
  esac
done
''',
        "chown": f'#!/bin/bash\n[ "{failing_command}" = chown ] && exit 1\nexit 0\n',
        "chmod": f'#!/bin/bash\n[ "{failing_command}" = chmod ] && exit 1\nexit 0\n',
    }
    for name, body in stubs.items():
        path = binaries / name
        path.write_text(body, encoding="utf-8")
        path.chmod(0o755)
    dump_dir = tmp_path / "backups" / "pg"
    environment = {
        **os.environ,
        "PATH": f"{binaries}:{os.environ['PATH']}",
        "PGDUMP_DIR": str(dump_dir),
        "RAW_DIR": str(tmp_path / "missing-raw"),
    }

    completed = subprocess.run(
        ["/bin/bash", str(BACKUP)],
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )

    assert completed.returncode != 0
    assert f"FAIL: {message}" in completed.stdout
    assert not list(dump_dir.glob("glasswell-*.dump"))
    assert not list(dump_dir.glob("glasswell-*.manifest.json"))
    assert "OK: backup complete" not in completed.stdout
