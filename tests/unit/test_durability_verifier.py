"""The host verifier's durability assertions, and the constants it must not drift from.

`verify.sh` and `status/collector.py` observe the same three receipts from opposite sides — one
in shell on the host, one in Python for the served surface. Nothing but these tests stops their
paths and staleness bounds from drifting apart.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from glasswell.status import collector

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
VERIFY = ROOT / "infra" / "verify.sh"
INSTALL = ROOT / "infra" / "install.sh"
BACKUP = ROOT / "infra" / "backup" / "glasswell-backup.sh"
RECOVERY = ROOT / "infra" / "backup" / "glasswell-recovery-drill.sh"
DURABLE_WRITE = ROOT / "infra" / "backup" / "glasswell-durable-write.py"


def shell_value(path: Path, name: str) -> str:
    match = re.search(rf"^{name}=(\S+)$", path.read_text(), re.MULTILINE)
    assert match, f"{name}= not found in {path}"
    return match.group(1)


def test_verify_reads_the_restore_receipt_rather_than_only_the_timer():
    text = VERIFY.read_text()
    assert "printf 'restore drill proof\\n'" in text
    for fragment in (
        'assert "restore drill result" passed',
        'assert "restore drill schema heads agree" true',
        'assert "restore proof scratch cleanup" true',
    ):
        assert fragment in text


def test_verify_compares_the_receipt_schema_head_to_the_live_head():
    """The drill pins no version, so a pass against a stale dump is invisible without this."""
    text = VERIFY.read_text()
    section = text.split('assert "restore proof schema head equals the live head"', 1)[1]
    section = section.split("assert ", 1)[0]
    assert "select coalesce(max(version), 0) from public.schema_migrations" in section
    assert 'receipt_field "$RESTORE_RESULT" restored_schema_version' in section


def test_verify_bounds_receipt_age_so_a_receipt_that_stopped_updating_fails():
    text = VERIFY.read_text()
    collapsed = re.sub(r"\s*\\\n\s*", " ", text)
    assert 'receipt_freshness "$RESTORE_RESULT" "$RESTORE_PROOF_MAX_AGE_DAYS"' in collapsed
    assert 'fresh "${restore_verdict:-unreadable}"' in text
    # A future completion time is its own verdict, so a clock skew cannot read as fresh.
    freshness = text.split("receipt_freshness() {", 1)[1].split("\nPY", 1)[0]
    assert 'verdict = "future"' in freshness
    assert 'verdict = "stale"' in freshness


@pytest.mark.parametrize(
    ("shell_name", "python_name"),
    [
        ("RESTORE_PROOF_MAX_AGE_DAYS", "RESTORE_RESULT_STALE_AFTER"),
        ("OFFSITE_RECEIPT_MAX_AGE_DAYS", "OFFSITE_RECEIPT_STALE_AFTER"),
    ],
)
def test_staleness_bounds_do_not_drift_between_the_shell_and_the_collector(
    shell_name: str, python_name: str
) -> None:
    assert int(shell_value(VERIFY, shell_name)) == getattr(collector, python_name).days


@pytest.mark.parametrize(
    ("shell_name", "python_name"),
    [
        ("RESTORE_RESULT", "DEFAULT_RESTORE_RESULT"),
        ("OFFSITE_RECEIPT", "DEFAULT_OFFSITE_RECEIPT"),
        ("RECOVERY_RESULT", "DEFAULT_RECOVERY_RESULT"),
    ],
)
def test_receipt_paths_do_not_drift_between_the_shell_and_the_collector(
    shell_name: str, python_name: str
) -> None:
    assert shell_value(VERIFY, shell_name) == str(getattr(collector, python_name))


def test_verify_asserts_the_offsite_push_without_claiming_a_read_back():
    text = VERIFY.read_text()
    assert "printf 'offsite copy\\n'" in text
    assert 'assert "offsite push result" passed' in text
    assert 'assert "offsite receipt states its send-side limit" send_side_only' in text
    # The generation equality is what catches a receipt that stopped being republished.
    assert 'assert "offsite receipt covers the newest local dump generation"' in text
    assert "$(newest_dump_generation)" in text
    # The write-only grant is stated where the assertions are, not only in the runbook.
    preamble = text.split("printf 'offsite copy\\n'", 1)[0].rsplit("\n\n", 1)[-1]
    assert "rrsync -wo" in preamble
    assert "write-only" in preamble


def test_the_head_comparison_waits_for_a_drill_that_postdates_the_newest_migration():
    """The drill is weekly; every migration deploy would otherwise red verify.sh until Sunday."""
    text = VERIFY.read_text()
    gate = text.split("restore_proof_covers_live_head() {", 1)[1].split("\n}", 1)[0]
    assert "max(applied_at)" in gate
    assert 'receipt_field "$RESTORE_RESULT" completed_at' in gate
    assert "(( completed_at > applied_at ))" in gate

    block = text.split("printf 'restore drill proof\\n'", 1)[1].split("printf 'offsite copy", 1)[0]
    assert "if restore_proof_covers_live_head; then" in block
    assert "predates the newest migration" in block
    # Only the head comparison waits. Everything receipt-internal stays unconditional.
    for unconditional in (
        'assert "restore drill result" passed',
        'assert "restore drill schema heads agree" true',
        'assert "restore proof scratch cleanup" true',
        'fresh "${restore_verdict:-unreadable}"',
    ):
        assert unconditional in block
        assert unconditional not in block.split("if restore_proof_covers_live_head; then", 1)[
            1
        ].split("fi", 1)[0]


def test_an_existing_offsite_receipt_is_asserted_whatever_the_readiness_test_says():
    """`install` resets mtime every deploy; a stale receipt must not hide behind that window."""
    text = VERIFY.read_text()
    section = text.split("printf 'offsite copy\\n'", 1)[1].split("printf 'replacement-vm", 1)[0]
    assert "[[ -e $OFFSITE_RECEIPT ]] || offsite_receipt_expected" in section


def test_offsite_assertions_wait_for_a_backup_run_made_with_the_publishing_script():
    """Otherwise the deploy that ships the receipt writer fails for want of a receipt it
    could not yet have written, and blocks itself."""
    text = VERIFY.read_text()
    gate = text.split("offsite_receipt_expected() {", 1)[1].split("\n}", 1)[0]
    assert 'stat -c %Y -- "$script"' in gate
    assert "ExecMainExitTimestamp" in gate
    # Mandatory once a run postdates the installed script; a deleted receipt fails from then on.
    assert "(( last_run > installed_at ))" in gate
    branch = text.split("printf 'offsite copy\\n'", 1)[1].split("\n\n", 1)[0]
    assert "$backup_enabled == enabled" in branch
    assert "offsite_receipt_expected" in branch


def test_verify_reports_the_unexercised_recovery_path_without_failing_on_it():
    """Hard-failing on a proof nobody can produce yet would red the verifier permanently."""
    text = VERIFY.read_text()
    branch = text.split("if [[ -e $RECOVERY_RESULT ]]; then", 1)[1].split("\nfi", 1)[0]
    else_branch = branch.split("else", 1)[1]
    assert "ok " in else_branch
    assert "NEVER been executed" in else_branch
    assert "bad " not in else_branch


def test_verify_asserts_units_in_both_directions():
    """DR-H5: the tree-walking loop cannot see a unit that exists only on the host."""
    text = VERIFY.read_text()
    forward = 'assert_true "$name installed and identical to the tree"'
    reverse = 'assert_true "$name is declared in the tree"'
    assert forward in text
    assert reverse in text
    reverse_loop = text.split(reverse, 1)[0].rsplit("for unit in", 1)[1]
    assert '"$UNIT_DIR"/glasswell-*.service' in reverse_loop
    assert '"$UNIT_DIR"/glasswell-*.timer' in reverse_loop
    assert text.index(forward) < text.index(reverse)


def test_installer_places_the_recovery_drill_and_the_durable_writer():
    text = INSTALL.read_text()
    for script in ("glasswell-recovery-drill.sh", "glasswell-durable-write.py"):
        assert script in text
    assert DURABLE_WRITE.exists()
    assert RECOVERY.exists()


def test_the_receipt_writers_share_one_durable_write_implementation():
    """A second hand-rolled atomic writer is a second place for the safety checks to rot."""
    for script in (BACKUP, RECOVERY):
        assert "$DURABLE_WRITE" in script.read_text()
    helper = DURABLE_WRITE.read_text()
    for guard in ("receipt parent has a symlink component", "receipt target is unsafe"):
        assert guard in helper
    assert "os.replace(temporary, target)" in helper


def test_the_recovery_drill_documents_that_it_has_never_been_executed():
    """An honest 'never run' beats an implied guarantee; this pins the wording in place."""
    header = RECOVERY.read_text().split("set -uo pipefail", 1)[0]
    assert "NEVER BEEN EXECUTED" in header.upper()
    for forbidden in ("proven", "verified end-to-end", "battle-tested"):
        assert forbidden not in header.lower()


def test_the_recovery_drill_refuses_the_production_database():
    text = RECOVERY.read_text()
    assert "PRODUCTION_DATABASE=glasswell" in text
    assert 'fail refuses_production_database' in text
