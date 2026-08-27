"""Pure snapshot boundary tests: atomic shape, age validation and path safety."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from glasswell.api.routers.status import _overall_state, load_snapshot
from glasswell.status.collector import write_snapshot
from glasswell.status.models import PlatformStatus, StatusSnapshot


def _snapshot(observed_at: datetime) -> StatusSnapshot:
    return StatusSnapshot(
        observed_at=observed_at,
        checks=[],
        datasets=[],
        jobs=[],
        platform=PlatformStatus(),
        disclosures=[],
    )


def test_snapshot_write_is_complete_and_owner_group_readable(tmp_path: Path) -> None:
    path = tmp_path / "status.json"
    snapshot = _snapshot(datetime(2026, 8, 26, 18, tzinfo=UTC))

    write_snapshot(snapshot, path)

    assert json.loads(path.read_text(encoding="utf-8"))["snapshot_version"] == 1
    assert path.stat().st_mode & 0o777 == 0o640
    assert not list(tmp_path.glob(".status.json.*"))


def test_snapshot_age_is_evaluated_from_observed_time_not_file_mtime(tmp_path: Path) -> None:
    path = tmp_path / "status.json"
    observed = datetime(2026, 8, 26, 17, tzinfo=UTC)
    write_snapshot(_snapshot(observed), path)

    loaded, state, _ = load_snapshot(path=path, now=observed + timedelta(hours=1))

    assert loaded is not None
    assert state == "stale"


def test_snapshot_loader_refuses_a_symlink(tmp_path: Path) -> None:
    target = tmp_path / "target.json"
    write_snapshot(_snapshot(datetime(2026, 8, 26, 18, tzinfo=UTC)), target)
    linked = tmp_path / "status.json"
    linked.symlink_to(target)

    loaded, state, _ = load_snapshot(path=linked, now=datetime(2026, 8, 26, 18, tzinfo=UTC))

    assert loaded is None
    assert state == "invalid"


def test_snapshot_loader_refuses_implausible_future_time(tmp_path: Path) -> None:
    now = datetime(2026, 8, 26, 18, tzinfo=UTC)
    path = tmp_path / "status.json"
    write_snapshot(_snapshot(now + timedelta(minutes=6)), path)

    loaded, state, _ = load_snapshot(path=path, now=now)

    assert loaded is None
    assert state == "invalid"


def test_stale_source_is_degraded_while_never_fetched_source_is_partial() -> None:
    assert _overall_state("current", [], [], [{"state": "stale"}], []) == "degraded"
    assert _overall_state("current", [], [], [{"state": "pending"}], []) == "partial"
