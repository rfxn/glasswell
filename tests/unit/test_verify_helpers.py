"""The four new `verify.sh` helpers, executed rather than grepped.

`tests/unit/test_durability_verifier.py` asserts that the assertions exist and that the
constants have not drifted; it reads `verify.sh` as text. That would catch a deleted line and
miss a helper that returns the wrong answer — and these helpers gate every deploy. So this
module extracts the assertion primitives and the durability helper block out of the real
`verify.sh` and runs them under `/bin/bash` against real files, the same way
`test_recovery_drill.py` runs the recovery script.
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
VERIFY = ROOT / "infra" / "verify.sh"

PRIMITIVES_START = "passed=0"
PRIMITIVES_END = "# `systemctl show -p Result`"
HELPERS_START = "# The three durability receipts share a shape"
HELPERS_END = "\nstatus_api_serves_current_snapshot() {"


def _extract(text: str, start: str, end: str) -> str:
    assert start in text, f"anchor missing from verify.sh: {start!r}"
    assert end in text, f"anchor missing from verify.sh: {end!r}"
    return start + text.split(start, 1)[1].split(end, 1)[0]


def run_helper(
    tmp_path: Path, command: str, stub_env: dict[str, str] | None = None, **config: str
) -> subprocess.CompletedProcess[str]:
    """Run `command` with verify.sh's real primitives and durability helpers in scope."""
    text = VERIFY.read_text()
    binaries = tmp_path / "bin"
    binaries.mkdir(exist_ok=True)

    # `${PSQL[@]}` and `systemctl` are the only host dependencies the helpers reach for.
    (binaries / "psql_stub").write_text(
        '#!/bin/bash\nprintf "%s\\n" "${STUB_SQL_ANSWER:-}"\n', encoding="utf-8"
    )
    (binaries / "psql_stub").chmod(0o755)
    (binaries / "systemctl").write_text(
        '#!/bin/bash\nprintf "%s\\n" "${STUB_LAST_RUN:-}"\n', encoding="utf-8"
    )
    (binaries / "systemctl").chmod(0o755)

    settings = {
        "VENV_PY": "python3",
        "PGDUMP_DIR": str(tmp_path / "pg"),
        "SBIN_DIR": str(tmp_path / "sbin"),
        "RESTORE_RESULT": str(tmp_path / "restore.json"),
        "OFFSITE_RECEIPT": str(tmp_path / "offsite.json"),
        **config,
    }
    script = "\n".join(
        [
            "#!/bin/bash",
            "set -uo pipefail",
            *(f'{name}="{value}"' for name, value in settings.items()),
            f'PSQL=("{binaries / "psql_stub"}")',
            _extract(text, PRIMITIVES_START, PRIMITIVES_END),
            _extract(text, HELPERS_START, HELPERS_END),
            command,
        ]
    )
    harness = tmp_path / "harness.sh"
    harness.write_text(script, encoding="utf-8")

    return subprocess.run(
        ["/bin/bash", str(harness)],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, **(stub_env or {}), "PATH": f"{binaries}:{os.environ['PATH']}"},
    )


def write_restore_receipt(tmp_path: Path, **overrides) -> Path:
    completed_at = overrides.pop("completed_at", datetime.now(UTC) - timedelta(hours=2))
    payload = {
        "result": "passed",
        "schema_match": True,
        "restored_schema_version": 54,
        "scratch_removed": True,
        "failure_detail": None,
        "dump": {"name": "glasswell-20260830T020825Z.dump", "bytes": 1_493_358_179},
        "completed_at": completed_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        **overrides,
    }
    path = tmp_path / "restore.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


class TestReceiptField:
    def test_reads_scalars_booleans_and_dotted_paths(self, tmp_path: Path) -> None:
        write_restore_receipt(tmp_path)
        result = run_helper(
            tmp_path,
            'receipt_field "$RESTORE_RESULT" result\n'
            'receipt_field "$RESTORE_RESULT" schema_match\n'
            'receipt_field "$RESTORE_RESULT" restored_schema_version\n'
            'receipt_field "$RESTORE_RESULT" dump.name\n',
        )
        # A JSON true must reach the shell as `true`, because that is what the assert compares.
        assert result.stdout.split() == [
            "passed",
            "true",
            "54",
            "glasswell-20260830T020825Z.dump",
        ]

    @pytest.mark.parametrize("field", ["nope", "dump.nope", "result.name", "dump.name.deeper"])
    def test_an_absent_or_untraversable_field_yields_nothing(
        self, tmp_path: Path, field: str
    ) -> None:
        write_restore_receipt(tmp_path)
        # A missing key prints an empty line; traversing into a non-dict exits before printing.
        # `$(...)` strips the newline either way, so both reach the assert as an empty value.
        result = run_helper(tmp_path, f'receipt_field "$RESTORE_RESULT" {field}')
        assert result.stdout.strip() == ""
        assert result.stderr == ""

    def test_a_missing_or_malformed_receipt_yields_nothing(self, tmp_path: Path) -> None:
        """Fail-closed: the assert that reads an empty value reports the miss."""
        missing = run_helper(tmp_path, 'receipt_field "$RESTORE_RESULT" result')
        assert missing.stdout.strip() == ""

        (tmp_path / "restore.json").write_text("{not json", encoding="utf-8")
        malformed = run_helper(tmp_path, 'receipt_field "$RESTORE_RESULT" result')
        assert malformed.stdout.strip() == ""
        assert malformed.stderr == ""


class TestReceiptFreshness:
    @pytest.mark.parametrize(
        ("age", "bound", "expected"),
        [
            (timedelta(hours=2), "8", "2 fresh"),
            (timedelta(days=7, hours=23), "8", "191 fresh"),
            (timedelta(days=9), "8", "216 stale"),
            (timedelta(hours=-1), "8", "0 future"),
            # Inside the five-minute tolerance, so a little clock skew is not a failure.
            (timedelta(minutes=-2), "8", "0 fresh"),
        ],
    )
    def test_verdicts_at_and_across_the_bound(
        self, tmp_path: Path, age: timedelta, bound: str, expected: str
    ) -> None:
        write_restore_receipt(tmp_path, completed_at=datetime.now(UTC) - age)
        result = run_helper(tmp_path, f'receipt_freshness "$RESTORE_RESULT" {bound}')
        assert result.stdout.strip() == expected

    def test_an_unreadable_receipt_yields_no_verdict(self, tmp_path: Path) -> None:
        assert run_helper(tmp_path, 'receipt_freshness "$RESTORE_RESULT" 8').stdout.strip() == ""


class TestNewestDumpGeneration:
    def test_selects_by_mtime_not_by_name(self, tmp_path: Path) -> None:
        """The drill selects newest-by-mtime, so this must agree with it, not with sort order."""
        pg = tmp_path / "pg"
        pg.mkdir()
        lexically_last = pg / "glasswell-20260830T020825Z.manifest.json"
        lexically_first = pg / "glasswell-20260828T173819Z.manifest.json"
        for path in (lexically_last, lexically_first):
            path.write_text("{}", encoding="utf-8")
        old = datetime(2026, 8, 20).timestamp()
        os.utime(lexically_last, (old, old))

        result = run_helper(tmp_path, "newest_dump_generation")
        assert result.stdout.strip() == "20260828T173819Z"

    def test_an_empty_or_absent_dump_directory_yields_nothing(self, tmp_path: Path) -> None:
        assert run_helper(tmp_path, "newest_dump_generation").stdout.strip() == ""
        (tmp_path / "pg").mkdir()
        assert run_helper(tmp_path, "newest_dump_generation").stdout.strip() == ""


class TestOffsiteReceiptExpected:
    def test_a_run_after_the_installed_script_makes_the_receipt_mandatory(
        self, tmp_path: Path
    ) -> None:
        sbin = tmp_path / "sbin"
        sbin.mkdir()
        script = sbin / "glasswell-backup.sh"
        script.write_text("#!/bin/bash\n", encoding="utf-8")
        stamp = (datetime.now(UTC) - timedelta(days=2)).timestamp()
        os.utime(script, (stamp, stamp))

        result = run_helper(
            tmp_path,
            'offsite_receipt_expected; printf "status=%s\\n" "$?"',
            stub_env={"STUB_LAST_RUN": datetime.now(UTC).strftime("%a %Y-%m-%d %H:%M:%S UTC")},
        )
        assert result.stdout.strip() == "status=0"

    def test_a_deploy_that_just_reinstalled_the_script_excuses_the_absence(
        self, tmp_path: Path
    ) -> None:
        """`install` resets mtime on every deploy, which is the window this exists for."""
        sbin = tmp_path / "sbin"
        sbin.mkdir()
        (sbin / "glasswell-backup.sh").write_text("#!/bin/bash\n", encoding="utf-8")

        stamp = (datetime.now(UTC) - timedelta(days=1)).strftime("%a %Y-%m-%d %H:%M:%S UTC")
        result = run_helper(
            tmp_path,
            'offsite_receipt_expected; printf "status=%s\\n" "$?"',
            stub_env={"STUB_LAST_RUN": stamp},
        )
        assert result.stdout.strip() == "status=1"

    def test_a_backup_that_never_ran_excuses_the_absence(self, tmp_path: Path) -> None:
        sbin = tmp_path / "sbin"
        sbin.mkdir()
        (sbin / "glasswell-backup.sh").write_text("#!/bin/bash\n", encoding="utf-8")
        result = run_helper(tmp_path, 'offsite_receipt_expected; printf "status=%s\\n" "$?"')
        assert result.stdout.strip() == "status=1"

    def test_an_uninstalled_script_excuses_the_absence(self, tmp_path: Path) -> None:
        result = run_helper(tmp_path, 'offsite_receipt_expected; printf "status=%s\\n" "$?"')
        assert result.stdout.strip() == "status=1"


class TestRestoreProofCoversLiveHead:
    """BLOCKER-1's readiness wait: the deploy that lands a migration must not fail on it."""

    def _run(self, tmp_path: Path, applied_at: datetime, completed_at: datetime) -> str:
        write_restore_receipt(tmp_path, completed_at=completed_at)
        return run_helper(
            tmp_path,
            'restore_proof_covers_live_head; printf "status=%s\\n" "$?"',
            stub_env={"STUB_SQL_ANSWER": applied_at.strftime("%Y-%m-%d %H:%M:%S+00")},
        ).stdout.strip()

    def test_a_drill_after_the_newest_migration_compares_heads(self, tmp_path: Path) -> None:
        now = datetime.now(UTC)
        assert self._run(tmp_path, now - timedelta(days=3), now - timedelta(hours=2)) == "status=0"

    def test_a_migration_deployed_after_the_last_weekly_drill_holds_the_comparison(
        self, tmp_path: Path
    ) -> None:
        """The horizon's own 055+ migrations land days before the next Sunday drill."""
        now = datetime.now(UTC)
        assert self._run(tmp_path, now - timedelta(hours=1), now - timedelta(days=3)) == "status=1"

    def test_an_unreadable_receipt_holds_the_comparison_rather_than_asserting(
        self, tmp_path: Path
    ) -> None:
        result = run_helper(
            tmp_path,
            'restore_proof_covers_live_head; printf "status=%s\\n" "$?"',
            stub_env={"STUB_SQL_ANSWER": "2026-08-01 00:00:00+00"},
        )
        # The receipt's own safety and freshness asserts report the miss; this must not crash.
        assert result.stdout.strip() == "status=1"


class TestAssertReceiptIsSafe:
    def _failures(self, tmp_path: Path) -> int:
        result = run_helper(
            tmp_path,
            'assert_receipt_is_safe "restore proof" "$RESTORE_RESULT"\n'
            'printf "failed=%s\\n" "$failed"',
        )
        return int(result.stdout.strip().rsplit("failed=", 1)[1])

    def test_a_world_writable_receipt_fails(self, tmp_path: Path) -> None:
        write_restore_receipt(tmp_path).chmod(0o666)
        assert self._failures(tmp_path) >= 1

    def test_a_symlinked_receipt_fails(self, tmp_path: Path) -> None:
        """The receipt is written by root and read by the product user; a symlink is a forge."""
        real = tmp_path / "elsewhere.json"
        real.write_text("{}", encoding="utf-8")
        (tmp_path / "restore.json").symlink_to(real)
        assert self._failures(tmp_path) >= 1

    def test_an_absent_receipt_fails(self, tmp_path: Path) -> None:
        assert self._failures(tmp_path) >= 1


GUARD_START = "    # The double-run guard's own connection."
# The line the guard block ends at, not the prose above it: anchoring an extraction on a
# comment makes every correction to that comment a seven-test failure, which is what happened
# when the posture assertion below it was widened to every jurisdiction (gate-tx H-6).
GUARD_END = '    launching="$('


def test_the_double_run_guard_is_given_a_dsn_from_the_file_and_not_from_the_environment(
    tmp_path: Path,
) -> None:
    """The deploy invokes verify.sh over a non-interactive ssh command, whose environment
    carries no DSN at all: verify reaches PostgreSQL as `postgres` everywhere else. Without
    this the permanent guard exits 1 on every deploy and reports a double-run hazard that is
    not there."""
    verify = VERIFY.read_text(encoding="utf-8")
    fragment = _extract(verify, GUARD_START, GUARD_END)
    env_file = tmp_path / "scheduler.env"
    env_file.write_text(
        "GLASSWELL_DSN=postgresql:///glasswell?host=/var/run/postgresql&user=glasswell_scheduler\n"
    )
    stub = tmp_path / "python-stub"
    stub.write_text(
        '#!/bin/bash\n'
        'if [[ " $* " == *" --timer-owned "* ]]; then\n'
        '  printf "glasswell.marts.neighbors\\n"; exit 0\n'
        'fi\n'
        'printf "%s\\n" "${GLASSWELL_DSN:-UNSET}" > "$SEEN"\n'
        '[[ -n ${GLASSWELL_DSN:-} ]] || { printf "no database DSN\\n"; exit 1; }\n'
        'exit 0\n'
    )
    stub.chmod(0o755)
    seen = tmp_path / "seen"
    script = tmp_path / "guard.sh"
    script.write_text(
        _extract(verify, PRIMITIVES_START, PRIMITIVES_END)
        + f'\nVENV_PY={stub}\nSCHEDULER_ENV={env_file}\n'
        + fragment
        + '\nprintf "failed=%s\\n" "$failed"\n'
    )
    result = subprocess.run(
        ["/bin/bash", str(script)],
        capture_output=True,
        text=True,
        env={"PATH": os.environ["PATH"], "SEEN": str(seen)},
        check=False,
    )

    assert "failed=0" in result.stdout, result.stdout + result.stderr
    assert seen.exists(), "the guard never ran"
    assert seen.read_text().strip().startswith("postgresql:///glasswell"), seen.read_text()


def guard_stub(tmp_path: Path, body: str) -> Path:
    stub = tmp_path / "python-stub"
    stub.write_text(
        "#!/bin/bash\n"
        'if [[ " $* " == *" --timer-owned "* ]]; then\n'
        '  printf "glasswell.marts.neighbors\\n"; exit 0\n'
        "fi\n" + body
    )
    stub.chmod(0o755)
    return stub


def run_guard_block(tmp_path: Path, stub: Path) -> subprocess.CompletedProcess[str]:
    verify = VERIFY.read_text(encoding="utf-8")
    env_file = tmp_path / "scheduler.env"
    env_file.write_text("GLASSWELL_DSN=postgresql:///glasswell?host=/var/run/postgresql\n")
    script = tmp_path / "guard.sh"
    script.write_text(
        _extract(verify, PRIMITIVES_START, PRIMITIVES_END)
        + f"\nVENV_PY={stub}\nSCHEDULER_ENV={env_file}\n"
        + _extract(verify, GUARD_START, GUARD_END)
    )
    return subprocess.run(
        ["/bin/bash", str(script)], capture_output=True, text=True,
        env={"PATH": os.environ["PATH"]}, check=False,
    )


HAZARD_CLAIM = "would double-run with an installed timer"
# The four ways the guard can fail to check, each with the status cli.py returns for it. The
# reviewer executed the peer-auth case against the real fragment and got the hazard sentence.
NOT_CHECKED = [
    ("no DSN", 3, "no DSN, so nothing was checked"),
    ("peer auth", 4, "connection failed: FATAL:  Peer authentication failed"),
    ("registry unreadable", 5, "the registry could not be read, so nothing was checked"),
    ("no timer set", 6, "no installed timer drives any entry point"),
]


@pytest.mark.parametrize(("label", "status", "message"), NOT_CHECKED)
def test_the_guard_never_reports_a_hazard_for_a_check_it_could_not_run(
    tmp_path: Path, label: str, status: int, message: str
) -> None:
    """Read the status, never the prose: a message match cannot tell "no launch row resolved"
    from "I never reached the database"."""
    stub = guard_stub(tmp_path, f'printf "%s\\n" "{message}"; exit {status}\n')

    result = run_guard_block(tmp_path, stub)

    assert "FAIL" in result.stdout, f"{label} was not reported at all: {result.stdout}"
    assert HAZARD_CLAIM not in result.stdout, f"{label} was reported as a double-run hazard"
    assert f"exit {status}" in result.stdout, result.stdout


def test_the_guard_reports_a_real_hazard_as_one(tmp_path: Path) -> None:
    """The one status that is a claim about rows, and it has to still be made."""
    stub = guard_stub(tmp_path, 'printf "marts_neighbors_probe\\n"; exit 1\n')

    result = run_guard_block(tmp_path, stub)

    assert HAZARD_CLAIM in result.stdout, result.stdout
    assert "marts_neighbors_probe" in result.stdout


def test_the_guard_passes_only_on_a_clean_zero(tmp_path: Path) -> None:
    stub = guard_stub(tmp_path, "exit 0\n")

    result = run_guard_block(tmp_path, stub)

    assert "FAIL" not in result.stdout, result.stdout
    assert "no launch row names an entry point a timer already drives" in result.stdout


def test_the_dead_message_arm_is_gone(tmp_path: Path) -> None:
    """`could not take` was matched by verify.sh and emitted by nothing in the tree."""
    assert "could not take" not in VERIFY.read_text(encoding="utf-8")
