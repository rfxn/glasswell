"""The per-well monthly series for a jurisdiction that files below the well and rolls nothing up.

New Mexico's OCD promotes 17.6 M completion-pool filings over 70,024 wells and not one
`entity_type = 'well'` row, so no per-well figure exists to serve. Summing in the client would
be a served-looking number with no derivation; summing into `canonical` would invent a filing
the regulator never made; a view over rows carrying different derivation ids has no single
handle to resolve. A mart reads canonical and writes marts, which is the only layer this can
sit in, and it carries its own derivation so every point explains.

Registry-driven: it builds for every jurisdiction whose `production_grain` rule registers a
`served_rollup`, so a sixth pool-grain state is a rule spec key rather than a module.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import date
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
from glasswell.lineage.jurisdictions import load_jurisdictions
from glasswell.lineage.serialization import hash_payload

PRODUCTION_GRAIN = "production_grain"
SERVED_ROLLUP = "sum_over_pools"
POOL_GRAIN_ENTITY = "well_completion_pool"

# The two a sum admits, the same pair marts/cumulatives.py admits and for the same reason: a
# withheld month and an absent one are not filings to add, and adding them as the zero they are
# stored with would turn a regulator's silence into a measured zero.
ADMITTED_NULL_SEMANTICS = ("reported", "reported_zero")

# canonical stream -> the served column this mart fills. `liquid` is the served liquids column
# and its basis is the jurisdiction's own liquids rule, not this module's: New Mexico's
# cr_nm_wcproduction_liquids_1 files condensate as its own stream and does not fold it into oil,
# so a New Mexico `liquid` row is oil as filed and the response says so through _basis.
# Condensate is not summed here because no surface serves it: the well and pool series both
# carry oil, gas and water.
MART_STREAM_OF: dict[str, str] = {"oil": "liquid", "gas": "gas", "water": "water"}


class RollupRegistrationError(RuntimeError):
    """A registration's grain rule is unreadable or its spec is out of bounds."""


@dataclass(frozen=True, slots=True)
class RollupRegistration:
    jurisdiction_code: str
    state_code: str
    rule_id: str


@dataclass(frozen=True, slots=True)
class RollupRefresh:
    derivation_id: str
    jurisdiction_code: str
    state_code: str
    rule_id: str
    rows: int
    api10s: int
    first_month: date | None
    last_month: date | None
    excluded_filings: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "derivation_id": self.derivation_id,
            "jurisdiction_code": self.jurisdiction_code,
            "state_code": self.state_code,
            "rule_id": self.rule_id,
            "rows": self.rows,
            "api10s": self.api10s,
            "first_month": self.first_month.isoformat() if self.first_month else None,
            "last_month": self.last_month.isoformat() if self.last_month else None,
            "excluded_filings": self.excluded_filings,
        }


_RULE_SPECS = """
select rule_id, spec from lineage.conformance_rules where rule_id = any(%(rule_ids)s)
"""


def rollup_registrations(connection: psycopg.Connection) -> tuple[RollupRegistration, ...]:
    """Every registration whose grain rule registers a served rollup, resolved from the registry.

    Read through `load_jurisdictions` rather than off a join, so the mart resolves the same
    registration at the same knowledge cut the API does: a mart that built for a jurisdiction
    the API does not resolve would serve a sum from a decision nobody is serving.
    """
    registry = load_jurisdictions(connection)
    by_rule: dict[str, list[RollupRegistration]] = {}
    for row in registry:
        rule_id = row.rule(PRODUCTION_GRAIN)
        if rule_id is None:
            continue
        by_rule.setdefault(rule_id, []).append(
            RollupRegistration(
                jurisdiction_code=row.jurisdiction_code,
                state_code=str(row.identity_prefix),
                rule_id=rule_id,
            )
        )
    if not by_rule:
        return ()
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(_RULE_SPECS, {"rule_ids": sorted(by_rule)})
        specs = {row["rule_id"]: row["spec"] for row in cursor.fetchall()}
    chosen: list[RollupRegistration] = []
    for rule_id, registrations in sorted(by_rule.items()):
        spec = specs.get(rule_id)
        if spec is None or spec.get("served_rollup") is None:
            continue
        if spec.get("served_rollup") != SERVED_ROLLUP:
            raise RollupRegistrationError(
                f"{rule_id} registers served_rollup {spec['served_rollup']!r}, and"
                f" {SERVED_ROLLUP} is the only rollup this mart performs"
            )
        if spec.get("rolls_up_to_the_well") is not False:
            raise RollupRegistrationError(
                f"{rule_id} registers a served rollup and does not record"
                " rolls_up_to_the_well: false, so what canonical holds is unstated"
            )
        chosen.extend(registrations)
    return tuple(sorted(chosen, key=lambda item: item.state_code))


# The pool filings this mart sums, at the vintage the serving path reads them at: the ranking
# window is lineage/vintages.py's, so a restatement that moved one pool's month is summed as
# the restatement rather than beside it.
_SUMMED = """
with ranked as materialized (
    select p.api10, p.entity_key, p.production_month, p.stream, p.volume, p.unit,
           p.days_produced, p.null_semantics,
           row_number() over (
               partition by p.entity_type, p.entity_key, p.production_month, p.stream,
                            p.source_id
               order by p.report_vintage desc) as vintage_rank
      from canonical.production_monthly p
     where p.entity_type = %(entity_type)s
       and left(p.api10, 2) = %(state_code)s
),
filings as materialized (
    select r.api10, r.entity_key, r.production_month, m.mart_stream as stream, r.volume,
           r.unit, r.days_produced
      from ranked r
      join unnest(%(canonical_streams)s::text[], %(mart_streams)s::text[])
        as m(canonical_stream, mart_stream) on m.canonical_stream = r.stream
     where r.vintage_rank = 1
       and r.null_semantics = any(%(admitted)s)
),
summed as (
    select api10, %(state_code)s::text as state_code, production_month, stream,
           sum(volume) as volume, min(unit) as unit, max(days_produced) as days_produced,
           count(distinct entity_key)::int as pools_summed,
           %(aggregation)s::text as aggregation,
           count(distinct unit)::int as unit_variants
      from filings
     group by api10, production_month, stream
)
"""

_MEASURE = (
    _SUMMED
    + """
select (select count(*) from summed) as rows,
       (select coalesce(md5(string_agg(digest, ',' order by digest)), '')
          from (select md5(row(api10, state_code, production_month, stream, volume, unit,
                              days_produced, pools_summed, aggregation)::text) as digest
                  from summed) fingerprint) as digest,
       (select coalesce(max(unit_variants), 0) from summed) as unit_variants,
       (select count(*) from ranked r
         where r.vintage_rank = 1 and not (r.null_semantics = any(%(admitted)s))) as excluded
"""
)

_INSERT = (
    _SUMMED
    + """
insert into marts.well_pool_rollup
    (api10, state_code, production_month, stream, volume, unit, days_produced, pools_summed,
     aggregation, derivation_id)
select api10, state_code, production_month, stream, volume, unit, days_produced, pools_summed,
       aggregation, %(derivation_id)s
  from summed
"""
)

_SUMMARY = """
select count(distinct api10) as api10s, min(production_month) as first_month,
       max(production_month) as last_month
  from marts.well_pool_rollup
 where state_code = %(state_code)s
"""

_INPUT_DERIVATIONS = """
select d.derivation_id, d.created_vintage
  from lineage.derivations d
 where d.derivation_id in (
    select distinct p.derivation_id
      from canonical.production_monthly p
     where p.entity_type = %(entity_type)s and left(p.api10, 2) = %(state_code)s)
 order by d.derivation_id
"""


def _parameters(registration: RollupRegistration) -> dict[str, Any]:
    return {
        "entity_type": POOL_GRAIN_ENTITY,
        "state_code": registration.state_code,
        "canonical_streams": list(MART_STREAM_OF),
        "mart_streams": [MART_STREAM_OF[stream] for stream in MART_STREAM_OF],
        "admitted": list(ADMITTED_NULL_SEMANTICS),
        "aggregation": SERVED_ROLLUP,
    }


def _inputs(connection: psycopg.Connection, registration: RollupRegistration) -> list[InputRef]:
    """Every promotion the sum reads, cited one by one.

    One refresh means one handle for the whole series, which is coarser than a per-month one,
    so the edge set is the compensation: a reader who cannot ask which filings fed one month
    can still reach every promotion that fed the series.
    """
    with connection.cursor() as cursor:
        cursor.execute(
            _INPUT_DERIVATIONS,
            {"entity_type": POOL_GRAIN_ENTITY, "state_code": registration.state_code},
        )
        return [
            InputRef(kind="derivation", ref_id=derivation_id, as_of_vintage=vintage)
            for derivation_id, vintage in cursor.fetchall()
        ]


def refresh_registration(
    connection: psycopg.Connection, registration: RollupRegistration
) -> RollupRefresh:
    """Rebuild one jurisdiction's rows under one content-addressed derivation."""
    parameters = _parameters(registration)
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(_MEASURE, parameters)
        measured = cursor.fetchone()
    if measured["unit_variants"] > 1:
        raise RollupRegistrationError(
            f"{registration.jurisdiction_code} files one well-month-stream in more than one"
            " unit, and a sum across units is not a volume: the promotion is what has to"
            " reconcile them"
        )
    inputs = _inputs(connection, registration)
    with derive(
        "mart.refresh",
        output=OutputSpec(
            store="postgres",
            dataset="marts.well_pool_rollup",
            partition={"state": registration.jurisdiction_code},
            schema_version="1",
        ),
        params={
            "state_code": registration.state_code,
            "entity_type": POOL_GRAIN_ENTITY,
            "streams": dict(MART_STREAM_OF),
            "admitted_null_semantics": list(ADMITTED_NULL_SEMANTICS),
            "aggregation": SERVED_ROLLUP,
            "days_produced": "maximum over the pool filings, never the sum",
            # Stated rather than dropped: a filing this sum did not admit is a filing the
            # served series does not carry, and the count is where that is durable.
            "excluded_filings": int(measured["excluded"]),
            "input_derivations": len(inputs),
        },
        inputs=inputs,
        rules=[registration.rule_id],
    ) as context:
        context.set_rows(int(measured["rows"]))
        context.set_output_hash(hash_payload({"summed": measured["digest"]}))

    # The id is content-addressed and exists only once the block closes, so the rows carrying it
    # are written after it, the same shape the tile marts take.
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            "delete from marts.well_pool_rollup where state_code = %(state_code)s",
            {"state_code": registration.state_code},
        )
        cursor.execute(_INSERT, {**parameters, "derivation_id": context.derivation_id})
        cursor.execute(_SUMMARY, {"state_code": registration.state_code})
        summary = cursor.fetchone()

    session = current_session()
    emit(
        connection,
        "mart.refreshed",
        subject_type="derivation",
        subject_id=context.derivation_id,
        payload={
            "row_counts": {"well_pool_rollup": int(measured["rows"])},
            "jurisdiction_code": registration.jurisdiction_code,
            "rule_id": registration.rule_id,
        },
        correlation_id=session.correlation_id,
        occurred_at=session.clock.now(),
    )
    return RollupRefresh(
        derivation_id=context.derivation_id,
        jurisdiction_code=registration.jurisdiction_code,
        state_code=registration.state_code,
        rule_id=registration.rule_id,
        rows=int(measured["rows"]),
        api10s=int(summary["api10s"]),
        first_month=summary["first_month"],
        last_month=summary["last_month"],
        excluded_filings=int(measured["excluded"]),
    )


def refresh_well_pool_rollup(connection: psycopg.Connection) -> tuple[RollupRefresh, ...]:
    """Rebuild the mart for every jurisdiction that registers a served rollup, and no other."""
    return tuple(
        refresh_registration(connection, registration)
        for registration in rollup_registrations(connection)
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Refresh the per-well rollup mart for every jurisdiction that registers one."
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
            reports = refresh_well_pool_rollup(connection)
        connection.commit()
        print(json.dumps([report.to_dict() for report in reports], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
