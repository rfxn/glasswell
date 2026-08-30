"""One definition of a per-well cumulative, and the two marts that hold it.

A total with no coverage cannot say whether a zero is a filed zero or an absence, and it
cannot state a withheld month at all — those months never reach canonical, they are
quarantined. So the mart carries the six month classes beside the total, and they reconcile
to the span on every row (§5.1). Rebuilt, never appended (§3.0.1).
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

import psycopg
from psycopg.rows import dict_row

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

# Keyed by state so widening is a mapping entry rather than an edit. Texas withholding is
# field-level under cr_tx_ewa_measures_1 (053_tx_measure_withholding.sql:1-2), a different
# grain, so adding it is a reader as well as an entry — which is what this shape says.
WITHHOLDING_SOURCES: dict[str, tuple[tuple[str, str], ...]] = {
    "33": (("nd_mpr_xlsx", "confidential_withheld"),),
}
STATE_API_PREFIXES = tuple(WITHHOLDING_SOURCES)

MART_STREAMS = ("liquid", "gas", "water")
STREAM_UNITS = {"liquid": "bbl", "gas": "mcf", "water": "bbl"}
STREAM_BASIS = {"liquid": LIQUIDS_BASIS, "gas": None, "water": "water"}

OBSERVED = "observed"
NEVER_REPORTED = "never_reported"

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


PER_WELL_CUMULATIVE_CTE = f"""
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
     where entity_type = 'well' and api10 is not null
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

    def to_dict(self) -> dict[str, object]:
        return {
            "derivation_id": self.derivation_id,
            "row_counts": dict(self.row_counts),
            "snapshot_vintage": self.snapshot_vintage.isoformat()
            if self.snapshot_vintage
            else None,
            "states": list(self.states),
            "coverage_outcomes": dict(self.coverage_outcomes),
        }


_WELLS = """
select api10, state_code
  from canonical.wells_latest
 where state_code = any(%(states)s)
 order by api10
"""

_STREAM_TOTALS = f"""
select api10, {_MART_STREAM} as stream, sum(volume) as cum_volume
  from canonical.production_monthly_latest
 where entity_type = 'well' and api10 is not null
   and left(api10, 2) = any(%(states)s)
   and {cumulative_semantics_predicate()}
 group by 1, 2
"""

# One label per (well, mart stream, month): where two sources filed the same month, the
# strongest statement wins, so a reported month is never demoted by a second source's blank.
_STREAM_MONTHS = f"""
select api10, {_MART_STREAM} as stream, production_month, min({_CLASS_RANK}) as class_rank
  from canonical.production_monthly_latest
 where entity_type = 'well' and api10 is not null
   and left(api10, 2) = any(%(states)s)
 group by 1, 2, 3
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
     span_months, first_month, last_month, coverage_outcome, snapshot_vintage, derivation_id)
values (%(api10)s, %(state_code)s, %(stream)s, %(cum_volume)s, %(unit)s, %(basis)s,
        %(months_reported)s, %(months_reported_zero)s, %(months_no_report_stored)s,
        %(months_withheld_stored)s, %(months_absent)s, %(span_months)s, %(first_month)s,
        %(last_month)s, %(coverage_outcome)s, %(snapshot_vintage)s, %(derivation_id)s)
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
    pairs = [pair for entries in WITHHOLDING_SOURCES.values() for pair in entries]
    return sorted({pair[0] for pair in pairs}), sorted({pair[1] for pair in pairs})


def _canonical_inputs(connection: psycopg.Connection) -> list[InputRef]:
    with connection.cursor() as cursor:
        cursor.execute(_INPUT_DERIVATIONS)
        return [
            InputRef(kind="derivation", ref_id=derivation_id, as_of_vintage=vintage)
            for derivation_id, vintage in cursor.fetchall()
        ]


def _collect(connection: psycopg.Connection) -> dict[str, Any]:
    states = {"states": list(STATE_API_PREFIXES)}
    sources, reasons = _withholding_pairs()
    totals: dict[tuple[str, str], Decimal | None] = {}
    for row in _rows(connection, _STREAM_TOTALS, states):
        totals[(row["api10"], row["stream"])] = row["cum_volume"]
    months: dict[tuple[str, str], dict[date, str]] = {}
    for row in _rows(connection, _STREAM_MONTHS, states):
        months.setdefault((row["api10"], row["stream"]), {})[row["production_month"]] = (
            _RANK_LABELS[int(row["class_rank"])]
        )
    withheld: dict[str, dict[date, str | None]] = {}
    for row in _rows(connection, _WITHHELD_MONTHS, {**states, "sources": sources,
                                                    "reasons": reasons}):
        withheld.setdefault(row["api10"], {})[row["production_month"]] = row["rule_id"]
    with connection.cursor() as cursor:
        cursor.execute(_SNAPSHOT_VINTAGE, states)
        snapshot_vintage = cursor.fetchone()[0]
    return {
        "wells": _rows(connection, _WELLS, states),
        "totals": totals,
        "months": months,
        "withheld": withheld,
        "snapshot_vintage": snapshot_vintage,
    }


def _cumulative_rows(collected: dict[str, Any]) -> list[dict[str, Any]]:
    snapshot_vintage = collected["snapshot_vintage"]
    rows: list[dict[str, Any]] = []
    for well in collected["wells"]:
        api10 = well["api10"]
        withheld_months = collected["withheld"].get(api10, {})
        well_months: dict[date, str] = {}
        for stream in MART_STREAMS:
            well_months |= collected["months"].get((api10, stream), {})
        span = filed_span(well_months, withheld_months)
        outcome = NEVER_REPORTED if span[0] is None else OBSERVED
        for stream in MART_STREAMS:
            counts = month_class_counts(
                span, collected["months"].get((api10, stream), {}), withheld_months
            )
            rows.append(
                {
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
            )
    return rows


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
    cumulatives = _cumulative_rows(collected)
    withholding = _withholding_rows(collected)
    snapshot_vintage = collected["snapshot_vintage"]
    outcomes = {OBSERVED: 0, NEVER_REPORTED: 0}
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
                state: [list(pair) for pair in pairs]
                for state, pairs in WITHHOLDING_SOURCES.items()
            },
            "state_api_prefixes": list(STATE_API_PREFIXES),
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
        states=STATE_API_PREFIXES,
        coverage_outcomes=outcomes,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Refresh the per-well cumulative marts.")
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--env-id", default=None, help="override the fingerprinted env id")
    parser.add_argument("--code-version", default=None)
    arguments = parser.parse_args(argv)

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
