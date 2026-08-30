"""Whether a well is actually producing, as its conformance rules define it (R8).

Administrative status and production evidence are different facts. The regulator's `active`
says a permit is in good standing; this module answers the separate question of whether the
well shows up in the production filings, and it answers it from rule rows rather than from a
predicate buried in a query. Every parameter below — the window, the streams, what counts as
evidence — is read from `lineage.conformance_rules` at serve time.

Marts read canonical only (blueprint §3.0.1): the classes are computed live from
canonical.production_monthly, so they cannot go stale against a mart refresh.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

import psycopg
from psycopg.rows import dict_row

PRODUCING = "producing"
NOT_PRODUCING = "not_producing"
UNKNOWN = "unknown"
PRODUCING_CLASSES = (PRODUCING, NOT_PRODUCING, UNKNOWN)

WINDOW_RULE = "cr_producing_window_1"
STREAMS_RULE = "cr_producing_streams_1"
EVIDENCE_RULE = "cr_producing_evidence_1"
PRODUCING_RULE_IDS = (WINDOW_RULE, STREAMS_RULE, EVIDENCE_RULE)

# canonical.production_monthly's own check constraints. The spec reaches SQL, so it is held to
# the column vocabulary rather than trusted for having arrived in a registry row.
CANONICAL_STREAMS = ("condensate", "gas", "oil", "water")
CANONICAL_NULL_SEMANTICS = ("no_report", "reported", "reported_zero", "withheld")

# reported_zero is a filed zero and withheld is a regulator holding the number back. Neither is
# evidence that a well produced, and admitting either here would invert the answer rather than
# widen it, so the loader refuses them instead of letting a rule edit choose.
NEVER_QUALIFYING_SEMANTICS = ("no_report", "reported_zero", "withheld")

ANCHORS = ("latest_available_production_month",)

MONTHS_IN_YEAR = 12


class ProducingPolicyError(RuntimeError):
    """A producing rule row is missing or its spec is out of bounds. Never defaulted around."""


@dataclass(frozen=True, slots=True)
class ProducingPolicy:
    window_months: int
    anchor: str
    streams: tuple[str, ...]
    liquids_basis: str
    evidence_semantics: tuple[str, ...]
    rule_ids: tuple[str, ...] = PRODUCING_RULE_IDS


def _require(condition: object, message: str) -> None:
    if not condition:
        raise ProducingPolicyError(message)


def _vocabulary(
    values: object, *, allowed: tuple[str, ...], field: str, forbidden: tuple[str, ...] = ()
) -> tuple[str, ...]:
    _require(isinstance(values, (list, tuple)) and values, f"{field} must be a non-empty list")
    chosen = tuple(sorted({str(value) for value in values}))  # type: ignore[union-attr]
    for value in chosen:
        _require(value in allowed, f"{field} names {value!r}, which is not one of {allowed}")
        _require(value not in forbidden, f"{field} names {value!r}, which is never evidence")
    return chosen


def policy_from_specs(
    *, window: dict[str, Any], streams: dict[str, Any], evidence: dict[str, Any]
) -> ProducingPolicy:
    """Validate three rule specs into the policy the serving path executes."""
    months = window.get("window_months")
    _require(
        isinstance(months, int) and not isinstance(months, bool) and months >= 1,
        f"window_months must be a positive integer, not {months!r}",
    )
    anchor = str(window.get("anchor", ""))
    _require(
        anchor in ANCHORS,
        f"anchor {anchor!r} is not one of {ANCHORS}; the wall clock is not an anchor because"
        " the monthly report runs months behind it",
    )
    basis = streams.get("liquids_basis")
    _require(isinstance(basis, str) and basis, "liquids_basis is required on the streams rule")
    return ProducingPolicy(
        window_months=int(str(months)),
        anchor=anchor,
        streams=_vocabulary(
            streams.get("qualifying_streams"),
            allowed=CANONICAL_STREAMS,
            field="qualifying_streams",
        ),
        liquids_basis=str(basis),
        evidence_semantics=_vocabulary(
            evidence.get("qualifying_null_semantics"),
            allowed=CANONICAL_NULL_SEMANTICS,
            field="qualifying_null_semantics",
            forbidden=NEVER_QUALIFYING_SEMANTICS,
        ),
    )


_LOAD_SPECS = """
select rule_id, spec
  from lineage.conformance_rules
 where rule_id = any(%(rule_ids)s)
   and effective_from <= current_date
   and (effective_to is null or effective_to > current_date)
"""


def load_producing_policy(connection: psycopg.Connection) -> ProducingPolicy:
    """R8: the definition is rows, so a missing row is a refusal, never an assumed default."""
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(_LOAD_SPECS, {"rule_ids": list(PRODUCING_RULE_IDS)})
        specs = {row["rule_id"]: row["spec"] for row in cursor.fetchall()}
    missing = [rule_id for rule_id in PRODUCING_RULE_IDS if rule_id not in specs]
    _require(not missing, f"the producing definition is not registered: {', '.join(missing)}")
    return policy_from_specs(
        window=specs[WINDOW_RULE], streams=specs[STREAMS_RULE], evidence=specs[EVIDENCE_RULE]
    )


# Well-level, because the classifier is: a lease or pool row filed for a newer month would
# move the window past every well and read the whole basin as idle.
_ANCHOR_MONTH = (
    "select max(production_month) as month from canonical.production_monthly"
    " where entity_type = 'well'"
)


def anchor_month(connection: psycopg.Connection, policy: ProducingPolicy) -> date | None:
    """The newest month anybody has filed. None where no production has been loaded at all."""
    _require(policy.anchor in ANCHORS, f"anchor {policy.anchor!r} has no reader")
    with connection.cursor() as cursor:
        cursor.execute(_ANCHOR_MONTH)
        row = cursor.fetchone()
    return row[0] if row else None


def window_start(anchor: date | None, policy: ProducingPolicy) -> date | None:
    """The window is inclusive of its anchor: three months is the anchor and the two before."""
    if anchor is None:
        return None
    offset = anchor.month - 1 - (policy.window_months - 1)
    return date(anchor.year + offset // MONTHS_IN_YEAR, offset % MONTHS_IN_YEAR + 1, 1)


# The class, in one expression, so the collection filter and the summary count cannot drift
# into disagreeing about what producing means.
#
# `distinct on … report_vintage desc` is what makes a restatement land: a month revised down to
# zero must not still answer producing on the strength of the row it superseded (DIR-2).
#
# The inner select is deliberately not narrowed to the qualifying streams — `having count(*)`
# asks whether the well filed *anything* that window. A well lifting only water has filed, so
# it is not-producing (a fact); a well that filed nothing is unknown (an absence). Collapsing
# those two would report an absence of evidence as evidence of absence.
_CLASS_SQL = """
case
  when {state_code} = any(%(producing_lease_states)s) then '{unknown}'
  else coalesce((
    select case when bool_or(l.volume > 0
                             and l.null_semantics = any(%(producing_evidence)s)
                             and l.stream = any(%(producing_streams)s))
                then '{producing}' else '{not_producing}' end
      from (select distinct on (p.production_month, p.stream)
                   p.volume, p.null_semantics, p.stream
              from canonical.production_monthly p
             where p.api10 = {api10}
               and p.entity_type = 'well'
               and p.production_month >= %(producing_window_start)s
             order by p.production_month, p.stream, p.report_vintage desc) l
     having count(*) > 0), '{unknown}')
end
"""


def class_expression(*, api10: str, state_code: str) -> str:
    return _CLASS_SQL.format(
        api10=api10,
        state_code=state_code,
        producing=PRODUCING,
        not_producing=NOT_PRODUCING,
        unknown=UNKNOWN,
    )


# DIR-3 read as a population rather than as one well's card: where no well-level series was ever
# observed, a state's wells have nothing to be absent from, and answering not_producing would
# libel every producing well in it — on the 2026-08 load that is 114,122 Texas wells the
# regulator calls active.
#
# Two registry reasons produce that absence and the query resolves both, because the *reason*
# differs and the *consequence* does not. A lease-reporting jurisdiction files above the well.
# New Mexico files below it: cr_nm_wcproduction_pool_rollup_1 records that its grain is
# well_completion_pool and that nothing rolls up, so a New Mexico well has 17.6M pool rows
# behind it and no well-level series to evaluate. Reading either from the registry is what keeps
# this a mapping decision with a row rather than a state code in a serving path.
_NO_WELL_SERIES_STATES = """
select distinct spec ->> 'state_code' as state_code
  from lineage.conformance_rules
 where spec ->> 'reporting_level' = 'lease'
   and (spec -> 'allocation_required')::boolean
   and (effective_to is null or effective_to > current_date)
   and spec ->> 'state_code' is not null
union
select distinct spec ->> 'state_code' as state_code
  from lineage.conformance_rules
 where spec ->> 'reporting_level' = 'well_completion_pool'
   and (spec -> 'rolls_up_to_the_well')::boolean is false
   and (effective_to is null or effective_to > current_date)
   and spec ->> 'state_code' is not null
 order by state_code
"""


def no_well_series_states(connection: psycopg.Connection) -> list[str]:
    """States whose registry says no well-level series exists, for either recorded reason."""
    with connection.cursor() as cursor:
        cursor.execute(_NO_WELL_SERIES_STATES)
        return [row[0] for row in cursor.fetchall()]



def producing_params(connection: psycopg.Connection, policy: ProducingPolicy) -> dict[str, Any]:
    """Every value `class_expression` binds, resolved once per request."""
    return {
        "producing_streams": list(policy.streams),
        "producing_evidence": list(policy.evidence_semantics),
        "producing_window_start": window_start(anchor_month(connection, policy), policy),
        "producing_lease_states": no_well_series_states(connection),
    }
