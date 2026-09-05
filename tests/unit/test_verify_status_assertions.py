"""The two claims `verify.sh` used to make as one, executed against real payloads.

`status_api_serves_current_snapshot` asserted four things and failed with one sentence:
"API rejected, omitted, or marked the freshly collected snapshot stale". On 2026-09-04 that
line went red on VM 111 while the snapshot was measurably current — the reds were
`allocation_conservation` and `crosswalk_agreement` unavailable and `allocation_error_bounds`
degraded, the empty-mart disclosures the Texas train ships by design between the deploy and
the load's Step 4. The failure text was a false statement about the host, and it named nothing
an operator could act on.

So the freshness claim and the health claim are separate assertions now, and the health one
names the ids it failed on. Both halves are extracted out of the real `verify.sh` and run
under `/bin/bash` with a stubbed `api_curl`, the way `test_verify_helpers.py` runs the
durability block — a grep would pass on a helper that returned the wrong answer.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
VERIFY = ROOT / "infra" / "verify.sh"
RUNBOOK = ROOT / "docs" / "runbook-tx-load.md"

BLOCK_START = "status_api_snapshot() {"
BLOCK_END = "\nprintf 'services\\n'"

UNREADABLE = "the snapshot could not be read"


def helpers() -> str:
    text = VERIFY.read_text(encoding="utf-8")
    assert BLOCK_START in text, f"anchor missing from verify.sh: {BLOCK_START!r}"
    assert BLOCK_END in text, f"anchor missing from verify.sh: {BLOCK_END!r}"
    return BLOCK_START + text.split(BLOCK_START, 1)[1].split(BLOCK_END, 1)[0]


def snapshot(
    snapshot_state: str = "current",
    observed_at: str | None = "2026-09-04T19:30:16Z",
    datasets: int = 25,
    checks: list[dict[str, str]] | None = None,
    jobs: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """The `/v1/status` envelope, at the shape `glasswell.status.models` really serves."""
    return {
        "data": {
            "snapshot_state": snapshot_state,
            "observed_at": observed_at,
            "datasets": [{"id": f"ds_{index}"} for index in range(datasets)],
            "checks": checks if checks is not None else [{"id": "api_reachable", "state": "ok"}],
            "jobs": jobs if jobs is not None else [{"id": "nd_mpr", "state": "ok"}],
        }
    }


def run(
    tmp_path: Path, call: str, payload: dict[str, Any] | None
) -> subprocess.CompletedProcess[str]:
    """`payload` None stubs a curl that fails, which is what a stopped API looks like here."""
    if payload is None:
        stub = "api_curl() { return 22; }"
    else:
        body = tmp_path / "status.json"
        body.write_text(json.dumps(payload), encoding="utf-8")
        stub = f'api_curl() {{ cat {body}; }}'

    script = tmp_path / "harness.sh"
    script.write_text(
        "\n".join(
            [
                "#!/bin/bash",
                "set -uo pipefail",
                'VENV_PY=python3',
                'API=http://localhost',
                'owner_key=not-the-real-key',
                stub,
                helpers(),
                call,
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return subprocess.run(
        ["/bin/bash", str(script)], capture_output=True, text=True, timeout=60
    )


class TestTheFreshnessClaim:
    """(a) — whether the snapshot on the wire is the one collection just wrote."""

    def test_a_current_snapshot_passes(self, tmp_path: Path) -> None:
        assert run(tmp_path, "status_api_serves_current_snapshot", snapshot()).returncode == 0

    def test_an_unavailable_check_is_not_staleness(self, tmp_path: Path) -> None:
        """The regression this split exists for. These three reds are the Texas train's
        empty-mart disclosures; the snapshot carrying them is current, and saying otherwise
        sent an operator looking at the collector."""
        payload = snapshot(
            checks=[
                {"id": "allocation_conservation", "state": "unavailable"},
                {"id": "crosswalk_agreement", "state": "unavailable"},
                {"id": "allocation_error_bounds", "state": "degraded"},
            ]
        )

        assert run(tmp_path, "status_api_serves_current_snapshot", payload).returncode == 0

    def test_a_degraded_job_is_not_staleness(self, tmp_path: Path) -> None:
        payload = snapshot(jobs=[{"id": "tx_pdq", "state": "degraded"}])

        assert run(tmp_path, "status_api_serves_current_snapshot", payload).returncode == 0

    @pytest.mark.parametrize(
        "payload",
        [
            pytest.param(snapshot(snapshot_state="stale"), id="stale"),
            pytest.param(snapshot(observed_at=None), id="no-observed-at"),
            pytest.param(snapshot(datasets=0), id="no-datasets"),
        ],
    )
    def test_a_snapshot_that_is_not_current_fails(
        self, tmp_path: Path, payload: dict[str, Any]
    ) -> None:
        assert run(tmp_path, "status_api_serves_current_snapshot", payload).returncode != 0

    def test_an_unreadable_snapshot_fails(self, tmp_path: Path) -> None:
        assert run(tmp_path, "status_api_serves_current_snapshot", None).returncode != 0

    def test_it_prints_nothing_at_all(self, tmp_path: Path) -> None:
        """`assert_true` owns the line. A helper that printed would interleave with it."""
        finished = run(tmp_path, "status_api_serves_current_snapshot", snapshot())

        assert finished.stdout == ""


class TestTheHealthClaim:
    """(b) — which checks and jobs are unhealthy, by name."""

    def test_a_clean_snapshot_prints_no_entry(self, tmp_path: Path) -> None:
        finished = run(tmp_path, "status_api_unhealthy_entries", snapshot())

        assert finished.returncode == 0
        assert finished.stdout.strip() == ""

    def test_every_failing_check_id_is_named(self, tmp_path: Path) -> None:
        payload = snapshot(
            checks=[
                {"id": "api_reachable", "state": "ok"},
                {"id": "allocation_conservation", "state": "unavailable"},
                {"id": "allocation_error_bounds", "state": "degraded"},
            ]
        )

        finished = run(tmp_path, "status_api_unhealthy_entries", payload)

        assert finished.returncode == 0
        assert "allocation_conservation (unavailable)" in finished.stdout
        assert "allocation_error_bounds (degraded)" in finished.stdout
        assert "api_reachable" not in finished.stdout

    def test_a_degraded_job_is_named_and_marked_as_one(self, tmp_path: Path) -> None:
        """A check id and a job id can collide; the failure text has to say which it is."""
        payload = snapshot(
            checks=[{"id": "tx_pdq", "state": "ok"}],
            jobs=[{"id": "tx_pdq", "state": "degraded"}],
        )

        finished = run(tmp_path, "status_api_unhealthy_entries", payload)

        assert finished.stdout.strip() == "job:tx_pdq (degraded)"

    @pytest.mark.parametrize("state", ["pending", "not_instrumented", "refused"])
    def test_a_job_that_is_neither_ok_nor_degraded_is_not_a_failure(
        self, tmp_path: Path, state: str
    ) -> None:
        """`refused` is a job saying why it did not run, and a scheduler on `observe` refuses
        by design. Widening this to "not ok" would fail every deploy."""
        payload = snapshot(jobs=[{"id": "tx_pdq", "state": state}])

        finished = run(tmp_path, "status_api_unhealthy_entries", payload)

        assert finished.stdout.strip() == ""

    def test_an_unreadable_snapshot_is_a_non_zero_exit_not_an_empty_line(
        self, tmp_path: Path
    ) -> None:
        """Silence and health look identical on stdout, so the caller reads the exit status
        first. Getting that backwards would report a stopped API as a clean bill."""
        finished = run(tmp_path, "status_api_unhealthy_entries", None)

        assert finished.returncode != 0


class TestTheCallSite:
    def test_the_two_assertions_are_separate_lines(self) -> None:
        text = VERIFY.read_text(encoding="utf-8")

        assert "status_api_serves_current_snapshot" in text
        assert "status_api_unhealthy_entries" in text
        assert text.count('bad "$unhealthy_label"') == 2, (
            "an unreadable snapshot and a named failure are different failures"
        )

    def test_the_health_failure_text_carries_the_ids_and_not_a_fixed_sentence(self) -> None:
        """The defect was a static string that described a cause nobody had measured."""
        text = VERIFY.read_text(encoding="utf-8")
        call_site = text.split("unhealthy_label=", 1)[1].split("\n    fi", 1)[0]

        assert 'bad "$unhealthy_label" "$unhealthy_entries"' in call_site
        assert UNREADABLE in call_site

    def test_the_freshness_failure_text_no_longer_claims_to_know_about_checks(self) -> None:
        text = VERIFY.read_text(encoding="utf-8")
        freshness = text.split("status_api_serves_current_snapshot() {", 1)[1].split("\n}", 1)[0]

        assert 'item["state"]' not in freshness, (
            "the freshness helper reads a check state again; that is the joined assertion back"
        )


class TestTheDeliberateRed:
    """REG-V2. "verify.sh green, then the load" is circular for a train whose checks are the
    empty-mart disclosures the load itself clears."""

    def test_the_runbook_names_the_assertion_expected_red_before_the_load(self) -> None:
        text = RUNBOOK.read_text(encoding="utf-8")

        assert "no /v1/status check or job is degraded or unavailable" in text
        for check_id in (
            "allocation_conservation",
            "crosswalk_agreement",
            "allocation_error_bounds",
        ):
            assert check_id in text, f"{check_id} is not named as an expected red"

    def test_the_runbook_says_what_turns_it_green(self) -> None:
        text = RUNBOOK.read_text(encoding="utf-8")
        window = text.split("The window between the deploy and Step 4", 1)[1].split("---", 1)[0]

        assert "Step 4" in window
        assert "expected red" in window
