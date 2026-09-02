"""The cadence-driven scheduler: what is due, in what order, and what each tick observed.

A tick resolves the registry, computes the plan and appends what it decided. A job whose row
observes is recorded `would_run` and left to whatever already drives it -- the two pipeline
units the four legacy jurisdictions stay armed through. A job whose row launches is run, which
is admissible only where no installed timer drives the same entry point; `double_run_rows` is
the standing guard on that, and Colorado is the first jurisdiction registered under it.
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
