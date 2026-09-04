"""No row the seed resolves may launch, in any jurisdiction, from any builder.

A launching row is not a preference: `plan.py:363` rewrites a due `would_run` entry to `run`
for one, `runner.py:306` starts it, and `deploy.sh` re-arms `glasswell-scheduler.timer` on every
deploy, so one such row is one unattended run on the next tick. `launch` is therefore the
**scheduler launch-flip track**'s own act, and that track is the change that retires this file:
when the legacy pipeline timers are retired, the deploy's mart steps wait on scheduler runs,
`verify.sh` asserts the schedule a tick resolved, and a day of armed observe-mode ticks has been
compared against what the legacy timers ran, the flip appends its launching rows and deletes
this test in the same commit. Until then a `launch` row anywhere in the seed is a defect, and
this guard is what makes it one before a deploy finds out.

The founding rows a supersession has already corrected are history and stay declared: what is
read here is the row `lineage.job_schedules_as_of` would resolve, which is the row the planner
acts on.
"""

from __future__ import annotations

import importlib
import pkgutil

import pytest

import glasswell.seed
from glasswell.seed.schedules import SCHEDULES, _schedule_row, resolved_schedules

pytestmark = pytest.mark.unit

SCHEDULE_SHAPE = {"job_id", "cadence_note"}


def declared_schedule_tuples() -> dict[str, tuple[dict[str, object], ...]]:
    """Every module-level tuple of schedule rows in the seed package, by qualified name."""
    found: dict[str, tuple[dict[str, object], ...]] = {}
    for info in pkgutil.iter_modules(glasswell.seed.__path__):
        module = importlib.import_module(f"glasswell.seed.{info.name}")
        for name, value in vars(module).items():
            if not isinstance(value, tuple) or not value:
                continue
            if all(
                isinstance(row, dict) and set(row) >= SCHEDULE_SHAPE for row in value
            ):
                found[f"{info.name}.{name}"] = value
    return found


def test_no_row_the_seed_resolves_carries_launch() -> None:
    resolved = resolved_schedules()

    assert len(resolved) >= 30, "the seed resolved almost nothing; this guard would be vacuous"
    launching = sorted(
        job_id
        for job_id, row in resolved.items()
        if _schedule_row(row)["launch_mode"] != "observe"
    )

    assert launching == [], (
        f"{launching} resolve launch_mode='launch', so the next tick after a deploy starts them"
        " unattended. The posture is the launch-flip track's to change, not a registration's"
    )


def test_every_schedule_tuple_in_the_seed_is_one_this_guard_reads() -> None:
    """The 'every builder' half. A jurisdiction that declares its rows in a tuple of its own and
    splices them in elsewhere would otherwise be a launching row this file never looks at."""
    declared = declared_schedule_tuples()

    assert len(declared) >= 3, "no schedule tuple was discovered; the walk found nothing"
    seeded = [dict(row) for row in SCHEDULES]
    unreached = sorted(
        f"{name}[{index}] ({row['job_id']})"
        for name, rows in declared.items()
        for index, row in enumerate(rows)
        if dict(row) not in seeded
    )

    assert unreached == [], (
        f"{unreached} are declared as schedule rows and are not in SCHEDULES, so nothing seeds"
        " them and no posture guard reads them"
    )
