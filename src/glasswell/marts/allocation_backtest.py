"""What the equal-share method's error is, measured where both grains are published.

Montana files well-level and lease-level volumes as two disjoint families, so it is the one bed
this system has for scoring a split it cannot score in Texas. The study allocates the Montana
lease-unit total the way Texas is allocated, compares each share against the well row Montana
actually published, and publishes the distribution.

It reads canonical only. Montana's lease unit lives on a staging column, and a mart reading
staging is the breach `marts/producing.py:9-10` names — which is why the membership was
promoted into `canonical.lease_membership` before this module existed.

The bed is `entity_type = 'well'` regardless of `reporting_level` (N-25). Montana writes three
shapes for one well-month — per-pool rows, a well row aggregating them, and a well row where
the filings are not decomposable — and summing the pool rows *and* the aggregate would
double-count every decomposable well.

It publishes a control, not a decoration. Nothing here reaches a Texas figure until the
transferability measurement shows the distributions overlap; a band measured on another
regulator's leases over a horizon that has not been shown to match is a naked number with a
decoration on it.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_CEILING, Decimal

import psycopg
from psycopg.rows import dict_row

from glasswell.allocation.v0 import MODEL_ID, Eligible, allocate_lease_month, symmetric_error
from glasswell.db.dsn import add_dsn_argument, resolve_dsn
from glasswell.ingest.base import resolve_environment
from glasswell.lineage import (
    InputRef,
    OutputSpec,
    PostgresRecorder,
    current_session,
    derive,
    lineage_session,
    load_rules,
)
from glasswell.lineage.audit import emit
from glasswell.lineage.serialization import hash_payload

ERROR_RULE = "cr_alloc_v0_error_bounds_1"
PRECONDITION_RULE = "cr_mt_pru_reconciliation_1"
WELL_SOURCE_ID = "mt_bogc_well_production"
PRU_SOURCE_ID = "mt_bogc_pru_production"

# The bounds published are the tenth and ninetieth percentiles of the symmetric error, taken
# by nearest rank so every published bound is a value the study actually measured rather than
# an interpolation between two it did not. Over a small sample the band approaches the range,
# which is a property of the sample and is why lease_months_scored travels beside it.
LOWER_QUANTILE = Decimal("0.10")
UPPER_QUANTILE = Decimal("0.90")


def bed_jurisdiction(connection: psycopg.Connection) -> str:
    """Which regulator's filings the study is measured on, read from the rule that declares it.

    `cr_alloc_v0_error_bounds_1`'s spec carries `bed_jurisdiction`, so the bed is a published
    decision with a rationale and a date rather than a constant in this file -- which is also
    why a jurisdiction code does not appear in a serving module.
    """
    for rule in load_rules(connection, source_id=PRU_SOURCE_ID):
        if rule.rule_id == ERROR_RULE:
            return str(rule.spec["bed_jurisdiction"])
    raise LookupError(f"{ERROR_RULE} is not seeded, so the study has no declared bed")


@dataclass(frozen=True, slots=True)
class BacktestRefresh:
    derivation_id: str
    bed_jurisdiction: str = ""
    model_id: str = MODEL_ID
    wells_scored: int = 0
    lease_months_scored: int = 0
    months_measured: tuple[str, ...] = ()
    mean_wells_per_lease: str | None = None
    excluded_zero_zero_share: str | None = None
    error_lo: str | None = None
    error_hi: str | None = None
    p50: str | None = None
    transfer_outcome: str = "not_measured"
    lease_month_well_counts: Mapping[int, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "derivation_id": self.derivation_id,
            "bed_jurisdiction": self.bed_jurisdiction,
            "model_id": self.model_id,
            "wells_scored": self.wells_scored,
            "lease_months_scored": self.lease_months_scored,
            "months_measured": list(self.months_measured),
            "mean_wells_per_lease": self.mean_wells_per_lease,
            "excluded_zero_zero_share": self.excluded_zero_zero_share,
            "error_lo": self.error_lo,
            "error_hi": self.error_hi,
            "p50": self.p50,
            "transfer_outcome": self.transfer_outcome,
            "lease_month_well_counts": dict(self.lease_month_well_counts),
        }


# The bed. entity_type = 'well' regardless of reporting_level, which is the family that
# reconciles against the PRU total: summing the pool rows and the aggregate would double-count
# every decomposable well, and that is a mapping decision rather than a query.
_TRUTH = """
select api10, production_month, stream, sum(volume) as volume
  from canonical.production_monthly_latest
 where entity_type = 'well' and source_id = %(source_id)s and api10 is not null
   and null_semantics in ('reported', 'reported_zero')
 group by 1, 2, 3
"""

_LEASE_TOTALS = """
select entity_key as lease_key, production_month, stream, sum(volume) as volume
  from canonical.production_monthly_latest
 where entity_type = 'lease' and source_id = %(source_id)s
   and null_semantics in ('reported', 'reported_zero')
 group by 1, 2, 3
"""

_MEMBERSHIP = """
select lease_key, api10 from canonical.lease_membership
 where jurisdiction_code = %(jurisdiction)s
   and effective_from = (select max(effective_from) from canonical.lease_membership
                          where jurisdiction_code = %(jurisdiction)s)
"""

_INPUT_DERIVATIONS = """
select distinct derivation_id from canonical.production_monthly
 where source_id = any(%(sources)s)
"""

_INSERT = """
insert into marts.allocation_method_error (
    bed_jurisdiction, model_id, error_lo, error_hi, p50, wells_scored, lease_months_scored,
    months_measured, mean_wells_per_lease, excluded_zero_zero_share, snapshot_vintage,
    derivation_id)
values (%(bed_jurisdiction)s, %(model_id)s, %(error_lo)s, %(error_hi)s, %(p50)s,
        %(wells_scored)s, %(lease_months_scored)s, %(months_measured)s,
        %(mean_wells_per_lease)s, %(excluded_zero_zero_share)s, %(snapshot_vintage)s,
        %(derivation_id)s)
"""


def quantile(values: Sequence[Decimal], fraction: Decimal) -> Decimal | None:
    """Nearest-rank, so every published bound is a value the study actually measured."""
    if not values:
        return None
    ordered = sorted(values)
    position = (fraction * len(ordered)).to_integral_value(rounding=ROUND_CEILING)
    return ordered[max(1, min(len(ordered), int(position))) - 1]


def _rows(connection: psycopg.Connection, statement: str, params: Mapping[str, object]):
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(statement, dict(params))
        return cursor.fetchall()


def score(
    connection: psycopg.Connection, bed: str
) -> tuple[list[Decimal], dict[str, object]]:
    """One symmetric error per scored well-month, with what was excluded stated beside it."""
    membership: dict[str, list[str]] = {}
    for row in _rows(connection, _MEMBERSHIP, {"jurisdiction": bed}):
        membership.setdefault(str(row["lease_key"]), []).append(str(row["api10"]))

    truth: dict[tuple[str, date, str], Decimal] = {
        (str(row["api10"]), row["production_month"], str(row["stream"])): Decimal(row["volume"])
        for row in _rows(connection, _TRUTH, {"source_id": WELL_SOURCE_ID})
    }

    errors: list[Decimal] = []
    scored_wells: set[str] = set()
    months: set[str] = set()
    lease_months = 0
    excluded_zero_zero = 0
    well_counts: dict[int, int] = {}
    for row in _rows(connection, _LEASE_TOTALS, {"source_id": PRU_SOURCE_ID}):
        lease_key = str(row["lease_key"])
        month = row["production_month"]
        stream = str(row["stream"])
        wells = sorted(membership.get(lease_key, ()))
        if not wells:
            continue
        lease_months += 1
        months.add(month.strftime("%Y-%m"))
        well_counts[len(wells)] = well_counts.get(len(wells), 0) + 1
        shares = allocate_lease_month(
            Decimal(row["volume"]),
            [Eligible(api10=api10, eligible=True) for api10 in wells],
        )
        for share in shares:
            observed = truth.get((share.api10, month, stream))
            if observed is None:
                observed = Decimal(0)
            statistic = symmetric_error(share.volume, observed)
            if statistic is None:
                # Both sides zero: the commonest case rather than an edge, and the share of
                # them is served as its own figure rather than folded into a statistic that
                # cannot express it.
                excluded_zero_zero += 1
                continue
            errors.append(statistic)
            scored_wells.add(share.api10)

    considered = len(errors) + excluded_zero_zero
    mean_wells = (
        Decimal(sum(count * pairs for count, pairs in well_counts.items()))
        / Decimal(sum(well_counts.values()))
        if well_counts
        else None
    )
    return errors, {
        "wells_scored": len(scored_wells),
        "lease_months_scored": lease_months,
        "months_measured": tuple(sorted(months)),
        "excluded_zero_zero_share": (
            (Decimal(excluded_zero_zero) / Decimal(considered)).quantize(Decimal("0.0001"))
            if considered
            else None
        ),
        "mean_wells_per_lease": mean_wells.quantize(Decimal("0.001")) if mean_wells else None,
        "lease_month_well_counts": well_counts,
    }


def refresh_allocation_backtest(connection: psycopg.Connection) -> BacktestRefresh:
    """Publish the method study keyed by the bed it was measured on."""
    bed = bed_jurisdiction(connection)
    errors, measured = score(connection, bed)
    error_lo = quantile(errors, LOWER_QUANTILE)
    error_hi = quantile(errors, UPPER_QUANTILE)
    p50 = quantile(errors, Decimal("0.50"))
    with connection.cursor() as cursor:
        cursor.execute(
            _INPUT_DERIVATIONS, {"sources": [WELL_SOURCE_ID, PRU_SOURCE_ID]}
        )
        inputs = sorted(row[0] for row in cursor.fetchall())
        cursor.execute(
            "select max(report_vintage) from canonical.production_monthly"
            " where source_id = any(%s)",
            ([WELL_SOURCE_ID, PRU_SOURCE_ID],),
        )
        found = cursor.fetchone()
        snapshot_vintage = found[0] if found else None

    with derive(
        "alloc.apply",
        output=OutputSpec(
            store="postgres",
            dataset="marts.allocation_method_error",
            partition={"bed_jurisdiction": bed, "model_id": MODEL_ID},
            schema_version="1",
        ),
        params={
            "model_id": MODEL_ID,
            "bed_entity_predicate": "entity_type='well'",
            "statistic": "(allocated - truth) / (allocated + truth)",
            "quantiles": [str(LOWER_QUANTILE), str(UPPER_QUANTILE)],
            # The precondition measures that summing up agrees; it does not measure the error
            # of splitting down, so it is cited as the precondition and never as the
            # measurement.
            "precondition_rule": PRECONDITION_RULE,
            "transfer_outcome": "not_measured",
            **{
                key: (str(value) if isinstance(value, Decimal) else value)
                for key, value in measured.items()
                if key != "months_measured"
            },
            "months_measured": list(measured["months_measured"]),
        },
        inputs=[InputRef(kind="derivation", ref_id=item) for item in inputs],
        rules=[ERROR_RULE, PRECONDITION_RULE],
    ) as context:
        context.set_rows(1)
        context.set_output_hash(
            hash_payload(
                {
                    "errors": [str(value) for value in sorted(errors)],
                    "measured": json.dumps(measured, sort_keys=True, default=str),
                }
            )
        )

    with connection.cursor() as cursor:
        cursor.execute(
            "delete from marts.allocation_method_error"
            " where bed_jurisdiction = %s and model_id = %s",
            (bed, MODEL_ID),
        )
        cursor.execute(
            _INSERT,
            {
                "bed_jurisdiction": bed,
                "model_id": MODEL_ID,
                "error_lo": error_lo,
                "error_hi": error_hi,
                "p50": p50,
                "wells_scored": measured["wells_scored"],
                "lease_months_scored": measured["lease_months_scored"],
                "months_measured": list(measured["months_measured"]),
                "mean_wells_per_lease": measured["mean_wells_per_lease"],
                "excluded_zero_zero_share": measured["excluded_zero_zero_share"],
                "snapshot_vintage": snapshot_vintage
                or current_session().clock.now().date(),
                "derivation_id": context.derivation_id,
            },
        )

    session = current_session()
    emit(
        connection,
        "mart.refreshed",
        subject_type="derivation",
        subject_id=context.derivation_id,
        payload={"bed": bed, "errors_scored": len(errors)},
        correlation_id=session.correlation_id,
        occurred_at=session.clock.now(),
    )
    return BacktestRefresh(
        derivation_id=context.derivation_id,
        bed_jurisdiction=bed,
        wells_scored=int(measured["wells_scored"]),
        lease_months_scored=int(measured["lease_months_scored"]),
        months_measured=tuple(measured["months_measured"]),
        mean_wells_per_lease=str(measured["mean_wells_per_lease"])
        if measured["mean_wells_per_lease"] is not None
        else None,
        excluded_zero_zero_share=str(measured["excluded_zero_zero_share"])
        if measured["excluded_zero_zero_share"] is not None
        else None,
        error_lo=str(error_lo) if error_lo is not None else None,
        error_hi=str(error_hi) if error_hi is not None else None,
        p50=str(p50) if p50 is not None else None,
        lease_month_well_counts=measured["lease_month_well_counts"],
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Score allocation v0 against Montana, the one bed that publishes both grains."
    )
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
            report = refresh_allocation_backtest(connection)
        connection.commit()
        print(json.dumps(report.to_dict(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
