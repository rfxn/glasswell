"""The cadence-driven scheduler: what is due, in what order, and what each tick observed.

v0.77 ships observing. Every schedule row the registry seeds is `launch_mode='observe'`, so a
tick resolves the registry, computes the plan and appends `would_run` rows without launching
anything; the two pipeline units stay armed and remain the thing that actually runs. The launch
path, the per-job lock, the reconciler, the calendar rule and the tick budget are all built and
exercised through `--run`, so v0.78 is rows plus a green suite.
"""

from __future__ import annotations

from glasswell.scheduler.plan import PlanEntry, TickPlan, plan_tick
from glasswell.scheduler.units import (
    TRANSIENT_HARDENING,
    render_transient_argv,
    timer_owned_entry_points,
)

__all__ = [
    "TRANSIENT_HARDENING",
    "PlanEntry",
    "TickPlan",
    "plan_tick",
    "render_transient_argv",
    "timer_owned_entry_points",
]
