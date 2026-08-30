"""Vintage cohorts, keyed by the rule row that chose the key (R8).

Spud year and completion-anchor year are different charts, not two names for one, so which
one a cohort is keyed on is a decision with a rationale and a date. It lives in
cr_nd_vintage_cohort_1 and is read here at serve time; no query decides it.

Marts read canonical only (blueprint §3.0.1): the rollup groups marts.well_cumulatives by a
key read from canonical.wells_latest, and touches no staging table.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import psycopg
from psycopg.rows import dict_row

from glasswell.marts.cumulatives import MART_STREAMS, STATE_API_PREFIXES
from glasswell.marts.land_metrics import support_distribution

COHORT_RULE = "cr_nd_vintage_cohort_1"
COHORT_KEYS = ("completion_anchor_year", "spud_year")

# Measured on the deployed instance 2026-08-30 over 94 ND spud-year cohorts: producing-well
# counts run 0 to 2,553, and the PLSS section scale puts 73 of the 94 in one bucket. These
# order-of-magnitude bands put no bucket over half the population.
COHORT_BANDS: tuple[tuple[int, int | None, str], ...] = (
    (0, 0, "0"),
    (1, 9, "1-9"),
    (10, 99, "10-99"),
    (100, 999, "100-999"),
    (1000, None, "1000+"),
)

SUPPORT_SCALE_NOTE = (
    "Cohort scale, not the PLSS section scale used by the land-grid rollups. A section holds a"
    " handful of wells and a vintage cohort holds hundreds, so the section bands put 73 of the"
    " 94 ND cohorts in one class and told a reader nothing. Two grains, two stated scales."
)

# The Williston basin does not stop at the state line; this population does. Said inside
# `data` so it survives a copy-paste of the payload.
POPULATION_SCOPE_DETAIL = (
    "The Williston basin extends into Montana (API prefix 25). No Montana well is in this"
    " population, so a basin-level reading of these cohorts is truncated at the state line."
    " North Dakota is complete."
)

SPACING_ASSUMPTION_REASON = (
    "A vintage cohort is a population of drilled wells, not a set of admissible slots; no"
    " spacing is assumed and none is implied. Slot inventory is E17/P8 and is not served here."
)

__all__ = [
    "COHORT_BANDS",
    "COHORT_KEYS",
    "COHORT_RULE",
    "POPULATION_SCOPE_DETAIL",
    "SPACING_ASSUMPTION_REASON",
    "SUPPORT_SCALE_NOTE",
    "CohortPolicy",
    "CohortPolicyError",
    "cohort_rollup",
    "load_cohort_policy",
    "policy_from_spec",
    "support_distribution",
]


class CohortPolicyError(RuntimeError):
    """The cohort rule row is missing or its spec is out of bounds. Never defaulted around."""


@dataclass(frozen=True, slots=True)
class CohortPolicy:
    cohort_key: str
    cohort_key_field: str
    null_cohort_label: str
    vintage_read_at: str
    rule_ids: tuple[str, ...] = (COHORT_RULE,)


def _require(condition: object, message: str) -> None:
    if not condition:
        raise CohortPolicyError(message)


def policy_from_spec(spec: dict[str, Any]) -> CohortPolicy:
    key = str(spec.get("cohort_key", ""))
    _require(key in COHORT_KEYS, f"cohort_key {key!r} is not one of {COHORT_KEYS}")
    label = str(spec.get("null_cohort_label", "") or "")
    _require(
        label,
        "null_cohort_label is required: a cohort of wells the regulator published no key for"
        " is served as its own cohort, never dropped and never folded into a year",
    )
    field = str(spec.get("cohort_key_field", "") or "")
    _require(field, "cohort_key_field must name the column the key is read from")
    return CohortPolicy(
        cohort_key=key,
        cohort_key_field=field,
        null_cohort_label=label,
        vintage_read_at=str(spec.get("vintage_read_at", "") or "wells_latest_effective_row"),
    )


_LOAD_SPEC = """
select rule_id, spec
  from lineage.conformance_rules
 where rule_id = %(rule_id)s
   and effective_from <= current_date
   and (effective_to is null or effective_to > current_date)
"""


def load_cohort_policy(connection: psycopg.Connection) -> CohortPolicy:
    """R8: the definition is a row, so a missing row is a refusal, never an assumed default."""
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(_LOAD_SPEC, {"rule_id": COHORT_RULE})
        found = cursor.fetchall()
    _require(found, f"the cohort key is not registered: {COHORT_RULE}")
    return policy_from_spec(dict(found[0])["spec"])


# The key expression per admitted cohort_key. Written here rather than composed at the call
# site so a key the policy admits always has a reader, and one it does not cannot reach SQL.
_KEY_EXPRESSIONS = {
    "spud_year": "extract(year from w.spud_date)::int",
    "completion_anchor_year": "extract(year from w.completion_date)::int",
}

_ROLLUP = """
select {key} as cohort_year,
       count(distinct w.api10) as wells,
       count(distinct w.api10) filter (where c.months_reported > 0) as producing_wells,
       sum(c.cum_volume) filter (where c.stream = 'liquid') as liquid_bbl,
       sum(c.cum_volume) filter (where c.stream = 'gas') as gas_mcf,
       sum(c.cum_volume) filter (where c.stream = 'water') as water_bbl,
       max(c.snapshot_vintage) as snapshot_vintage,
       max(w.effective_from) as spud_dates_read_at
  from canonical.wells_latest w
  join marts.well_cumulatives c on c.api10 = w.api10
 where w.state_code = any(%(states)s)
 group by 1
 order by 1 nulls last
"""

_DERIVATIONS = """
select distinct derivation_id from marts.well_cumulatives order by derivation_id
"""


def cohort_rollup(
    connection: psycopg.Connection, policy: CohortPolicy
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """The cohorts, and the population facts the response has to state beside them."""
    expression = _KEY_EXPRESSIONS.get(policy.cohort_key)
    _require(expression is not None, f"cohort_key {policy.cohort_key!r} has no reader")
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(_ROLLUP.format(key=expression), {"states": list(STATE_API_PREFIXES)})
        found = [dict(row) for row in cursor.fetchall()]
        cursor.execute(_DERIVATIONS)
        derivations = [row["derivation_id"] for row in cursor.fetchall()]
    cohorts = [
        {
            "cohort_year": row["cohort_year"],
            "cohort_key_semantics": (
                policy.cohort_key if row["cohort_year"] is not None else policy.null_cohort_label
            ),
            "wells": int(row["wells"]),
            "producing_wells": int(row["producing_wells"]),
            "totals": {
                stream: row[column]
                for stream, column in zip(
                    MART_STREAMS, ("liquid_bbl", "gas_mcf", "water_bbl"), strict=True
                )
            },
        }
        for row in found
    ]
    population = {
        "snapshot_vintage": max((row["snapshot_vintage"] for row in found), default=None),
        "spud_dates_read_at": max((row["spud_dates_read_at"] for row in found), default=None),
        "derivation_ids": derivations,
        "support_distribution": support_distribution(
            [cohort["producing_wells"] for cohort in cohorts], COHORT_BANDS
        ),
    }
    return cohorts, population
