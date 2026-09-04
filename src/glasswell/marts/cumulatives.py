"""One definition of a per-well cumulative, and the two marts that hold it.

A total with no coverage cannot say whether a zero is a filed zero or an absence, and it
cannot state a withheld month at all — those months never reach canonical, they are
quarantined. So the mart carries the six month classes beside the total, and they reconcile
to the span on every row (§5.1). Rebuilt, never appended (§3.0.1).
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Collection, Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

import psycopg
from psycopg.rows import dict_row

from glasswell.db.dsn import add_dsn_argument, resolve_dsn
from glasswell.ingest.base import resolve_environment
from glasswell.lineage import (
    InputRef,
    OutputSpec,
    PostgresRecorder,
    current_session,
    derive,
    lineage_session,
)
from glasswell.lineage.audit import emit
from glasswell.lineage.serialization import hash_payload
from glasswell.seed.jurisdictions import JURISDICTIONS, SERVING_JURISDICTION_RULES

NULL_SEMANTICS_RULE = "cr_nd_null_semantics_1"
LIQUIDS_RULE = "cr_nd_liquids_policy_1"
ROLLUP_RULE = "cr_nd_pool_rollup_1"

LIQUIDS_BASIS = "oil+condensate"

# The two the total admits. A no_report or withheld canonical row carries volume 0 by
# construction in both writers (ingest/nd_mpr.py:289-291, ingest/nm_ocd.py:846-847), so this
# moves no total today; it states what the total admits instead of relying on that fill value.
ADMITTED_NULL_SEMANTICS = ("reported", "reported_zero")

MONTH_CLASS_PARTS = (
    "reported",
    "reported_zero",
    "no_report_stored",
    "withheld_stored",
    "absent",
    "withheld_quarantined",
)

# Keyed by jurisdiction code so widening is a mapping entry rather than an edit, and resolved
# to an API prefix through the registry rather than spelling one here. Texas withholding is
# field-level under cr_tx_ewa_measures_1 (053_tx_measure_withholding.sql:1-2), a different
# grain, so adding it is a reader as well as an entry — which is what this shape says.
WITHHOLDING_SOURCES: dict[str, tuple[tuple[str, str], ...]] = {
    "ND": (("nd_mpr_xlsx", "confidential_withheld"),),
}
_PREFIX_OF = {
    str(row["jurisdiction_code"]): str(row["identity_prefix"]) for row in JURISDICTIONS
}
WITHHOLDING_BY_PREFIX: dict[str, tuple[tuple[str, str], ...]] = {
    _PREFIX_OF[code]: sources for code, sources in WITHHOLDING_SOURCES.items()
}

# The jurisdictions the cumulative mart covers, and the population every figure built from it
# is stated over. Kept separate from WITHHOLDING_SOURCES on purpose: a state can be in scope
# with nothing withheld, and registering a withholding source is not a decision to widen
# coverage (land_metrics.py:128-131 draws the same line for the PLSS grid).
#
# A registry dimension rather than a tuple, so widening the mart is a row with a rationale and
# an effective date like every other cross-source decision. The rule each registration names is
# the one that decides the jurisdiction writes a well-grain row at all -- observed or
# allocated. A jurisdiction in scope whose named rule decides neither would be entered from the
# well spine, match no month, and be published never_reported with its production sitting in
# canonical: a positive false claim rather than a gap.
#
# Restated for Texas, where the well-grain row is an allocation. The observed read is
# `entity_type = 'well'` over canonical; the allocated read is over
# marts.tx_allocated_production, which is a mart reading a mart -- admissible, and stated as
# such by marts/vintage_cohorts.py:7-8. What is never admissible is a mart reading staging.
# Every figure built from an allocated row states `basis: allocated` and names the model.
CUMULATIVES_SCOPE = "cumulatives_scope"
CUMULATIVE_JURISDICTIONS: tuple[str, ...] = tuple(
    str(row["jurisdiction_code"])
    for row in SERVING_JURISDICTION_RULES
    if row["decision"] == CUMULATIVES_SCOPE and row.get("serving", True)
)
STATE_API_PREFIXES: tuple[str, ...] = tuple(
    _PREFIX_OF[code] for code in CUMULATIVE_JURISDICTIONS
)

# The rule each registration names, so the mart can ask it what grain the jurisdiction writes.
SCOPE_RULE_OF: dict[str, str] = {
    str(row["jurisdiction_code"]): str(row["rule_id"])
    for row in SERVING_JURISDICTION_RULES
    if row["decision"] == CUMULATIVES_SCOPE and row.get("serving", True)
}

ALLOCATED_BASIS = "allocated"

# Which prefixes read the allocated mart is a question for the rules, not for this module, and
# a rule-id shape test would be a naked heuristic. The named rule's own spec says whether the
# well-grain row it admits is observed or allocated.
_SCOPE_BASIS = """
select rule_id, spec ->> 'cumulatives_basis' as basis
  from lineage.conformance_rules where rule_id = any(%(rule_ids)s)
"""


def allocated_prefixes(connection: psycopg.Connection) -> tuple[str, ...]:
    """The API prefixes whose well-grain cumulative row is an allocation."""
    if not SCOPE_RULE_OF:
        return ()
    declared = {
        row["rule_id"]: row["basis"]
        for row in _rows(
            connection, _SCOPE_BASIS, {"rule_ids": sorted(set(SCOPE_RULE_OF.values()))}
        )
    }
    return tuple(
        _PREFIX_OF[code]
        for code, rule_id in sorted(SCOPE_RULE_OF.items())
        if declared.get(rule_id) == ALLOCATED_BASIS
    )


MART_STREAMS = ("liquid", "gas", "water")
STREAM_UNITS = {"liquid": "bbl", "gas": "mcf", "water": "bbl"}
STREAM_BASIS = {"liquid": LIQUIDS_BASIS, "gas": None, "water": "water"}

OBSERVED = "observed"
NEVER_REPORTED = "never_reported"
OBSERVED_WITH_ALLOCATED = "observed_with_allocated"

MONTHS_IN_YEAR = 12

# The mart-stream fold, restated in SQL so the CTE and the refresh cannot disagree about it.
_MART_STREAM = "case when stream in ('oil', 'condensate') then 'liquid' else stream end"

_CLASS_RANK = (
    "case null_semantics when 'reported' then 1 when 'reported_zero' then 2"
    " when 'no_report' then 3 else 4 end"
)
_RANK_LABELS = {1: "reported", 2: "reported_zero", 3: "no_report", 4: "withheld"}


def cumulative_semantics_predicate() -> str:
    """The one predicate a cumulative admits, as SQL."""
    admitted = ", ".join(f"'{value}'" for value in ADMITTED_NULL_SEMANTICS)
    return f"null_semantics in ({admitted})"


def per_well_cumulative_cte(restrict_to: str | None = None) -> str:
    """The one definition of a per-well total; restrict_to bounds it to a CTE of api10s.

    A caller that joins the total against a bounded membership passes that CTE's name -
    identical output, but the mart stops reading the rows it would discard, 24.8M of them in
    the view after the New Mexico promotion.
    """
    membership = f"\n       and api10 in (select api10 from {restrict_to})" if restrict_to else ""
    allocated_membership = (
        f"\n       and api10 in (select api10 from {restrict_to})" if restrict_to else ""
    )
    return f"""
prod as (
    select api10,
           sum(volume) filter (
               where stream in ('oil', 'condensate')
                 and {cumulative_semantics_predicate()}) as liquid_bbl,
           sum(volume) filter (
               where stream = 'gas'
                 and {cumulative_semantics_predicate()}) as gas_mcf,
           sum(volume) filter (
               where stream = 'water'
                 and {cumulative_semantics_predicate()}) as water_bbl
      from canonical.production_monthly_latest
     where entity_type = 'well' and api10 is not null{membership}
     group by api10
     union all
    -- The allocated arm. A jurisdiction whose cumulatives_scope rule says its well-grain row
    -- is an allocation writes no entity_type = 'well' row in canonical at all, so reading
    -- canonical alone would publish never_reported over its whole spine. The mart-reads-mart
    -- ruling is what makes this admissible; a mart reading staging still is not.
    select api10,
           sum(volume) filter (where stream = 'liquid') as liquid_bbl,
           sum(volume) filter (where stream = 'gas') as gas_mcf,
           null::numeric as water_bbl
      from marts.tx_allocated_production
     where true{allocated_membership}
     group by api10)
"""


@dataclass(frozen=True, slots=True)
class MonthClasses:
    reported: int
    reported_zero: int
    no_report_stored: int
    withheld_stored: int
    absent: int
    withheld_quarantined: int
    span_months: int


def _months_between(first: date, last: date) -> int:
    return (last.year - first.year) * MONTHS_IN_YEAR + last.month - first.month + 1


def filed_span(
    labelled_months: Mapping[date, str], withheld_months: Collection[date]
) -> tuple[date | None, date | None]:
    """The axis /v1/wells/{api10}/production builds: every class unioned with the ledger."""
    union = {*labelled_months, *withheld_months}
    if not union:
        return None, None
    return min(union), max(union)


def month_class_counts(
    span: tuple[date | None, date | None],
    labelled_months: Mapping[date, str],
    withheld_months: Collection[date],
) -> MonthClasses:
    """The six parts of §5.1, which must add to the span.

    A ledger month takes precedence over a stored row: ND withholds the whole month, so no
    canonical row of any class exists for it, and letting both counts claim it would break
    the identity the mart is checked against.
    """
    first, last = span
    if first is None or last is None:
        return MonthClasses(0, 0, 0, 0, 0, 0, 0)
    span_months = _months_between(first, last)
    withheld = {month for month in withheld_months if first <= month <= last}
    stored = {
        label: 0 for label in ("reported", "reported_zero", "no_report", "withheld")
    }
    for month, label in labelled_months.items():
        if month in withheld or not first <= month <= last:
            continue
        stored[label] += 1
    counted = len(withheld) + sum(stored.values())
    return MonthClasses(
        reported=stored["reported"],
        reported_zero=stored["reported_zero"],
        no_report_stored=stored["no_report"],
        withheld_stored=stored["withheld"],
        absent=span_months - counted,
        withheld_quarantined=len(withheld),
        span_months=span_months,
    )


@dataclass(frozen=True, slots=True)
class CumulativesRefresh:
    derivation_id: str
    row_counts: Mapping[str, int]
    snapshot_vintage: date | None
    states: tuple[str, ...]
    coverage_outcomes: Mapping[str, int]
    # Allocated jurisdictions whose mart is empty on this instance: entered, they would have
    # published never_reported over their whole spine.
    skipped: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "derivation_id": self.derivation_id,
            "row_counts": dict(self.row_counts),
            "snapshot_vintage": self.snapshot_vintage.isoformat()
            if self.snapshot_vintage
            else None,
            "states": list(self.states),
            "coverage_outcomes": dict(self.coverage_outcomes),
            "skipped": list(self.skipped),
        }


_WELLS = """
select api10, state_code
  from canonical.wells_latest
 where state_code = any(%(states)s)
 order by api10
"""

_STREAM_TOTALS = f"""
select api10, {_MART_STREAM} as stream, sum(volume) as cum_volume, 0 as allocated_months
  from canonical.production_monthly_latest
 where entity_type = 'well' and api10 is not null
   and left(api10, 2) = any(%(states)s)
   and {cumulative_semantics_predicate()}
 group by 1, 2
 union all
select api10, stream, sum(volume) as cum_volume,
       count(distinct production_month) filter (where granularity = 'lease_allocated')
           as allocated_months
  from marts.tx_allocated_production
 where left(api10, 2) = any(%(allocated)s)
 group by 1, 2
"""

# The allocated months and the volume they carry, per well and mart stream. Served beside the
# total and never after it: a total that sums allocated months without saying so is the naked
# number this rule exists to prevent.
_ALLOCATED_MONTHS = """
select api10, stream,
       count(distinct production_month) filter (where granularity = 'lease_allocated')
           as allocated_months,
       sum(abs(volume)) filter (where granularity = 'lease_allocated') as allocated_volume,
       sum(abs(volume)) as total_volume,
       min(production_month) as first_month, max(production_month) as last_month,
       count(distinct production_month) as span_months
  from marts.tx_allocated_production
 where left(api10, 2) = any(%(allocated)s)
 group by 1, 2
"""

_ALLOCATED_WELLS = """
select distinct api10, left(api10, 2) as state_code
  from marts.tx_allocated_production
 where left(api10, 2) = any(%(allocated)s)
 order by api10
"""

# Which allocated jurisdictions have anything to be cumulated. Between `make deploy` and the
# manual load the allocated mart is empty, and an allocated jurisdiction entered from the well
# spine matches no month and publishes `never_reported` over its whole spine -- 359,421 Texas
# wells, three rows each -- which is the positive false claim the invariant above names by
# name. An empty mart is a jurisdiction that is not ready, not a jurisdiction that filed
# nothing (gate-tx H-10).
_ALLOCATED_PRESENT = """
select distinct left(api10, 2) as state_code
  from marts.tx_allocated_production
 where left(api10, 2) = any(%(allocated)s)
"""

# One label per (well, mart stream, month): where two sources filed the same month, the
# strongest statement wins, so a reported month is never demoted by a second source's blank.
#
# Ordered by api10 and read through a server-side cursor: this is the only unbounded relation
# the refresh touches — 7,141,506 groups on the 2026-08-30 ND load — and materialising it was a
# multi-gigabyte peak inside a deploy step that refuses on failure. One well is resident at a
# time (gate-t2-review MA-2).
_STREAM_MONTHS = f"""
select api10, {_MART_STREAM} as stream, production_month, min({_CLASS_RANK}) as class_rank
  from canonical.production_monthly_latest
 where entity_type = 'well' and api10 is not null
   and left(api10, 2) = any(%(states)s)
 group by 1, 2, 3
 order by 1
"""

_SNAPSHOT_VINTAGE = """
select max(report_vintage)
  from canonical.production_monthly
 where entity_type = 'well' and api10 is not null and left(api10, 2) = any(%(states)s)
"""

# The ledger predicate api/routers/production.py:72-79 reads, minus its as_of arm: a mart
# refresh has no knowledge cut to honour, so it reads the rows open now.
_WITHHELD_MONTHS = """
select row_payload ->> 'api10' as api10,
       (row_payload ->> 'production_month')::date as production_month,
       rule_id
  from lineage.quarantine_rows
 where source_id = any(%(sources)s)
   and reason_code = any(%(reasons)s)
   and row_payload ->> 'api10' is not null
   and row_payload ->> 'production_month' is not null
   and left(row_payload ->> 'api10', 2) = any(%(states)s)
   and state = 'open'
"""

_INPUT_DERIVATIONS = """
select derivation_id, created_vintage
  from lineage.derivations
 where derivation_id in (
    select derivation_id from canonical.wells
    union select derivation_id from canonical.production_monthly)
 order by derivation_id
"""

_INSERT_CUMULATIVE = """
insert into marts.well_cumulatives
    (api10, state_code, stream, cum_volume, unit, basis, months_reported,
     months_reported_zero, months_no_report_stored, months_withheld_stored, months_absent,
     span_months, first_month, last_month, coverage_outcome, allocated_months,
     allocated_share, snapshot_vintage, derivation_id)
values (%(api10)s, %(state_code)s, %(stream)s, %(cum_volume)s, %(unit)s, %(basis)s,
        %(months_reported)s, %(months_reported_zero)s, %(months_no_report_stored)s,
        %(months_withheld_stored)s, %(months_absent)s, %(span_months)s, %(first_month)s,
        %(last_month)s, %(coverage_outcome)s, %(allocated_months)s, %(allocated_share)s,
        %(snapshot_vintage)s, %(derivation_id)s)
"""

_INSERT_WITHHOLDING = """
insert into marts.well_withholding
    (api10, state_code, months_withheld, withheld_first_month, withheld_last_month, rule_ids,
     snapshot_vintage, derivation_id)
values (%(api10)s, %(state_code)s, %(months_withheld)s, %(withheld_first_month)s,
        %(withheld_last_month)s, %(rule_ids)s, %(snapshot_vintage)s, %(derivation_id)s)
"""


def _rows(connection: psycopg.Connection, statement: str, params: dict[str, Any]) -> list[dict]:
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(statement, params)
        return [dict(row) for row in cursor.fetchall()]


def _withholding_pairs() -> tuple[list[str], list[str]]:
    """Only the states in scope, so a source registered for a state the mart does not cover
    cannot reach the ledger query."""
    pairs = [
        pair for state in STATE_API_PREFIXES for pair in WITHHOLDING_BY_PREFIX.get(state, ())
    ]
    return sorted({pair[0] for pair in pairs}), sorted({pair[1] for pair in pairs})


def _canonical_inputs(connection: psycopg.Connection) -> list[InputRef]:
    with connection.cursor() as cursor:
        cursor.execute(_INPUT_DERIVATIONS)
        return [
            InputRef(kind="derivation", ref_id=derivation_id, as_of_vintage=vintage)
            for derivation_id, vintage in cursor.fetchall()
        ]


def _month_groups(
    connection: psycopg.Connection, states: dict[str, Any]
) -> Iterator[tuple[str, dict[str, dict[date, str]]]]:
    """One well's labelled months at a time, in api10 order, off a server-side cursor.

    The rows arrive grouped because the statement orders by api10, so a well is complete the
    moment a different one appears and nothing but the current well is ever resident.
    """
    with connection.cursor(name="gw_stream_months", row_factory=dict_row) as cursor:
        cursor.itersize = 10_000
        cursor.execute(_STREAM_MONTHS, states)
        current: str | None = None
        group: dict[str, dict[date, str]] = {}
        for row in cursor:
            if row["api10"] != current:
                if current is not None:
                    yield current, group
                current, group = row["api10"], {}
            group.setdefault(row["stream"], {})[row["production_month"]] = _RANK_LABELS[
                int(row["class_rank"])
            ]
        if current is not None:
            yield current, group


def _collect(connection: psycopg.Connection) -> dict[str, Any]:
    """Everything bounded by the well population. The month labels are not, so they stream."""
    allocated = list(allocated_prefixes(connection))
    present = {
        row["state_code"]
        for row in _rows(connection, _ALLOCATED_PRESENT, {"allocated": allocated})
    }
    skipped = [prefix for prefix in allocated if prefix not in present]
    allocated = [prefix for prefix in allocated if prefix in present]
    states = {"states": [item for item in STATE_API_PREFIXES if item not in skipped]}
    scoped = {**states, "allocated": allocated}
    sources, reasons = _withholding_pairs()
    totals: dict[tuple[str, str], Decimal | None] = {}
    for row in _rows(connection, _STREAM_TOTALS, scoped):
        key = (row["api10"], row["stream"])
        held = totals.get(key)
        totals[key] = row["cum_volume"] if held is None else held + (row["cum_volume"] or 0)
    allocation: dict[tuple[str, str], dict[str, Any]] = {
        (row["api10"], row["stream"]): row
        for row in _rows(connection, _ALLOCATED_MONTHS, {"allocated": allocated})
    }
    withheld: dict[str, dict[date, str | None]] = {}
    for row in _rows(connection, _WITHHELD_MONTHS, {**states, "sources": sources,
                                                    "reasons": reasons}):
        withheld.setdefault(row["api10"], {})[row["production_month"]] = row["rule_id"]
    with connection.cursor() as cursor:
        cursor.execute(_SNAPSHOT_VINTAGE, states)
        snapshot_vintage = cursor.fetchone()[0]
    # The allocated jurisdictions' wells are in the spine too, but their months live in the
    # mart, so the well list is the union: a well with an allocated share and no canonical row
    # would otherwise never be entered and would be missing rather than never_reported.
    wells = {row["api10"]: row for row in _rows(connection, _WELLS, states)}
    for row in _rows(connection, _ALLOCATED_WELLS, {"allocated": allocated}):
        wells.setdefault(row["api10"], row)
    return {
        "wells": [wells[api10] for api10 in sorted(wells)],
        "totals": totals,
        "allocation": allocation,
        "withheld": withheld,
        "snapshot_vintage": snapshot_vintage,
        "states": states,
        "allocated": allocated,
        "skipped": skipped,
    }


def _cumulative_rows(
    connection: psycopg.Connection, collected: dict[str, Any]
) -> Iterator[dict[str, Any]]:
    """Merge the well population against the streamed month labels; both are api10-ordered."""
    snapshot_vintage = collected["snapshot_vintage"]
    groups = _month_groups(connection, collected["states"])
    pending: tuple[str, dict[str, dict[date, str]]] | None = next(groups, None)
    for well in collected["wells"]:
        api10 = well["api10"]
        # The merge advances on a Python comparison over a Postgres ordering; the two agree
        # only while every key is the same width and ASCII. No DB-level CHECK enforces that,
        # and a short api10 would silently skip a well's months and report it never_reported.
        if len(api10) != 10 or not api10.isdigit():
            raise ValueError(
                f"api10 {api10!r} is not ten digits: the ordered merge cannot be trusted for it"
            )
        while pending is not None and pending[0] < api10:
            pending = next(groups, None)
        months: dict[str, dict[date, str]] = {}
        if pending is not None and pending[0] == api10:
            months = pending[1]
            pending = next(groups, None)
        withheld_months = collected["withheld"].get(api10, {})
        well_months: dict[date, str] = {}
        for stream in MART_STREAMS:
            well_months |= months.get(stream, {})
        allocated_here = {
            stream: collected["allocation"].get((api10, stream))
            for stream in MART_STREAMS
        }
        span = filed_span(well_months, withheld_months)
        if span[0] is None:
            bounds = [
                (row["first_month"], row["last_month"])
                for row in allocated_here.values()
                if row is not None
            ]
            if bounds:
                span = (min(first for first, _ in bounds), max(last for _, last in bounds))
        allocated_months_total = sum(
            int(row["allocated_months"] or 0)
            for row in allocated_here.values()
            if row is not None
        )
        if span[0] is None:
            outcome = NEVER_REPORTED
        elif allocated_months_total:
            # A history that mixes observed and allocated months is neither of the two words
            # that existed before it, and the share is served beside the total rather than
            # after it.
            outcome = OBSERVED_WITH_ALLOCATED
        else:
            outcome = OBSERVED
        for stream in MART_STREAMS:
            counts = month_class_counts(span, months.get(stream, {}), withheld_months)
            allocated_row = allocated_here.get(stream)
            allocated_months = int(allocated_row["allocated_months"] or 0) if allocated_row else 0
            allocated_share = None
            if allocated_row and allocated_row["total_volume"]:
                allocated_share = (
                    Decimal(allocated_row["allocated_volume"] or 0)
                    / Decimal(allocated_row["total_volume"])
                ).quantize(Decimal("0.0001"))
            yield {
                "allocated_months": allocated_months,
                "allocated_share": allocated_share,
                "api10": api10,
                "state_code": well["state_code"],
                "stream": stream,
                "cum_volume": collected["totals"].get((api10, stream)),
                "unit": STREAM_UNITS[stream],
                "basis": STREAM_BASIS[stream],
                "months_reported": counts.reported,
                "months_reported_zero": counts.reported_zero,
                "months_no_report_stored": counts.no_report_stored,
                "months_withheld_stored": counts.withheld_stored,
                "months_absent": counts.absent,
                "span_months": counts.span_months,
                "first_month": span[0],
                "last_month": span[1],
                "coverage_outcome": outcome,
                "snapshot_vintage": snapshot_vintage,
            }


def _withholding_rows(collected: dict[str, Any]) -> list[dict[str, Any]]:
    snapshot_vintage = collected["snapshot_vintage"]
    states = {well["api10"]: well["state_code"] for well in collected["wells"]}
    rows = []
    for api10 in sorted(collected["withheld"]):
        if api10 not in states:
            continue
        entries = collected["withheld"][api10]
        rows.append(
            {
                "api10": api10,
                "state_code": states[api10],
                "months_withheld": len(entries),
                "withheld_first_month": min(entries),
                "withheld_last_month": max(entries),
                "rule_ids": sorted({rule for rule in entries.values() if rule}),
                "snapshot_vintage": snapshot_vintage,
            }
        )
    return rows


def refresh_well_cumulatives(connection: psycopg.Connection) -> CumulativesRefresh:
    """Rebuild both cumulative marts under one content-addressed derivation."""
    collected = _collect(connection)
    cumulatives = list(_cumulative_rows(connection, collected))
    withholding = _withholding_rows(collected)
    snapshot_vintage = collected["snapshot_vintage"]
    outcomes = {OBSERVED: 0, NEVER_REPORTED: 0, OBSERVED_WITH_ALLOCATED: 0}
    for row in cumulatives:
        outcomes[row["coverage_outcome"]] += 1

    fingerprint = hash_payload(
        {
            "well_cumulatives": [
                json.dumps(row, sort_keys=True, default=str) for row in cumulatives
            ],
            "well_withholding": [
                json.dumps(row, sort_keys=True, default=str) for row in withholding
            ],
        }
    )
    with derive(
        "mart.refresh",
        output=OutputSpec(
            store="postgres",
            dataset="marts.well_cumulatives",
            partition={"states": ",".join(sorted(STATE_API_PREFIXES))},
            schema_version="1",
        ),
        params={
            "snapshot_vintage": snapshot_vintage.isoformat() if snapshot_vintage else None,
            "liquids_basis": LIQUIDS_BASIS,
            "null_semantics_admitted": list(ADMITTED_NULL_SEMANTICS),
            "month_class_parts": list(MONTH_CLASS_PARTS),
            "withholding_sources": {
                state: [list(pair) for pair in WITHHOLDING_BY_PREFIX.get(state, ())]
                for state in STATE_API_PREFIXES
            },
            "state_api_prefixes": list(collected["states"]["states"]),
            # Named in the params rather than dropped silently: a refresh that skipped a
            # jurisdiction has to say which, and the derivation is where that is durable.
            "skipped_prefixes": list(collected["skipped"]),
            "streams": list(MART_STREAMS),
            "coverage_outcomes": outcomes,
        },
        inputs=_canonical_inputs(connection),
        rules=[NULL_SEMANTICS_RULE, LIQUIDS_RULE, ROLLUP_RULE],
    ) as context:
        context.set_rows(len(cumulatives) + len(withholding))
        context.set_output_hash(fingerprint)

    # The id is content-addressed and only exists once the block closes, so the rows carrying
    # it are written after it — the same shape as the land-metrics mart.
    with connection.cursor() as cursor:
        cursor.execute("delete from marts.well_cumulatives")
        cursor.execute("delete from marts.well_withholding")
        cursor.executemany(
            _INSERT_CUMULATIVE,
            [{**row, "derivation_id": context.derivation_id} for row in cumulatives],
        )
        cursor.executemany(
            _INSERT_WITHHOLDING,
            [{**row, "derivation_id": context.derivation_id} for row in withholding],
        )

    row_counts = {
        "well_cumulatives": len(cumulatives),
        "well_withholding": len(withholding),
    }
    session = current_session()
    emit(
        connection,
        "mart.refreshed",
        subject_type="derivation",
        subject_id=context.derivation_id,
        payload={"row_counts": row_counts},
        correlation_id=session.correlation_id,
        occurred_at=session.clock.now(),
    )
    return CumulativesRefresh(
        derivation_id=context.derivation_id,
        row_counts=row_counts,
        snapshot_vintage=snapshot_vintage,
        states=tuple(collected["states"]["states"]),
        coverage_outcomes=outcomes,
        skipped=tuple(collected["skipped"]),
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Refresh the per-well cumulative marts.")
    add_dsn_argument(parser)
    parser.add_argument("--env-id", default=None, help="override the fingerprinted env id")
    parser.add_argument("--code-version", default=None)
    arguments = parser.parse_args(argv)
    arguments.dsn = resolve_dsn(arguments.dsn)

    with psycopg.connect(arguments.dsn) as connection:
        environment = resolve_environment(
            connection, env_id=arguments.env_id, code_version=arguments.code_version
        )
        with lineage_session(recorder=PostgresRecorder(connection), environment=environment):
            report = refresh_well_cumulatives(connection)
        connection.commit()
        print(json.dumps(report.to_dict(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
