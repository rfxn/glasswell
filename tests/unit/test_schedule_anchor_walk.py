"""The seed-time anchor walk, and the cycle it must refuse rather than recurse into.

Gate 2 guarantees every mart has an ingest *neighbour*; it does not bound a walk that follows
the first dependency, which may itself be a mart. The only structural guard on the edge table
forbids a self-loop, so a two-mart cycle satisfies gate 2 and would otherwise recurse until the
interpreter stopped it -- inside `seed_all`, which every deploy runs ungated.
"""

from __future__ import annotations

import pytest

from glasswell.seed import schedules
from glasswell.seed.schedules import JOBS, ScheduleSeedError, anchors, resolve_anchor

pytestmark = pytest.mark.unit


def test_every_registered_job_that_needs_an_anchor_resolves_one() -> None:
    resolved = anchors()

    assert set(resolved) == {
        str(job["job_id"]) for job in JOBS if job["kind"] != "maintenance"
    }
    assert all(source_id for source_id in resolved.values())


def test_a_mart_anchors_on_the_ingest_its_first_dependency_reaches() -> None:
    """marts_jurisdiction_counts depends only on marts, so the walk is two hops deep."""
    resolved = anchors()

    assert resolved["marts_jurisdiction_counts"] == resolved["marts_mt_wells"]
    assert resolved["marts_mt_wells"] == resolved["ingest_mt_bogc"]


def test_an_ingest_job_anchors_on_the_least_of_its_own_sources() -> None:
    assert resolve_anchor("ingest_nd_gis") == "nd_gis_directionals"


def test_a_two_mart_cycle_is_refused_by_name_and_not_recursed_into(monkeypatch) -> None:
    monkeypatch.setattr(
        schedules,
        "DEPENDENCIES",
        (
            ("marts_left", "marts_right", "changed", "left reads right"),
            ("marts_right", "marts_left", "changed", "right reads left"),
        ),
    )
    monkeypatch.setattr(schedules, "JOB_SOURCES", {})

    with pytest.raises(ScheduleSeedError) as refusal:
        resolve_anchor("marts_left")

    assert "marts_left" in str(refusal.value)
    assert "marts_right" in str(refusal.value)


def test_a_job_with_neither_a_source_nor_a_dependency_is_refused(monkeypatch) -> None:
    monkeypatch.setattr(schedules, "DEPENDENCIES", ())
    monkeypatch.setattr(schedules, "JOB_SOURCES", {})

    with pytest.raises(ScheduleSeedError, match="no anchor source exists"):
        resolve_anchor("marts_orphan")
