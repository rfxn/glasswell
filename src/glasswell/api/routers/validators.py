"""The three residual ledgers an allocation has to publish about itself.

Conservation is an invariant, and the two 4F.4 measurements are measurements; folding them
together would hide the invariant, which is why there are three blocks and not two. Every count
and every share is a figure with a handle, and the third block is a served refusal rather than
an omission: the RRC publishes no per-well Texas production at any grain, so there is no
independent truth to compare against and saying so is the honest answer.

A query parameter, not a Texas-shaped path: Kansas and Louisiana are both lease-grain and would
both arrive at a path frozen for the life of `/v1`.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from starlette.responses import JSONResponse

from glasswell.api.deps import Connection, ExplainEffect, jurisdictions, rows
from glasswell.api.errors import ProblemError, problem_responses
from glasswell.api.examples import GLOSSARY_KEY, request_example
from glasswell.api.provenance import register_response_figures
from glasswell.api.responses import EnvelopeModel, enveloped, inline_for
from glasswell.lineage.envelope import Figure, figure
from glasswell.marts.cumulatives import ALLOCATED_BASIS, CUMULATIVES_SCOPE
from glasswell.seed.jurisdictions import SERVING_JURISDICTION_RULES

router = APIRouter(tags=["validators"])

CROSSWALK_ROLE_RULE = "cr_tx_ewa_role_1"
ERROR_RULE = "cr_alloc_v0_error_bounds_1"
DEGRADED_AT = "unallocated_share_degraded_at"
GRAIN_DECISION = "production_grain"

COUNT_UNIT = "lease_months"
WELL_UNIT = "wells"
SHARE_UNIT = "share"

# Every cause the ledger admits, listed so a block that served only the causes it happened to
# hit would read as a clean run rather than as a partial one.
CAUSES = (
    "no_crosswalk_row",
    "all_wells_after_month",
    "all_wells_plugged_before_month",
    "no_eligible_well",
)

# The jurisdiction the example addresses, read out of the registrations rather than written
# as a rule id: a literal here is stranded the day a supersession moves the rule (gate-tx
# RV-3). A registration that allocates is one whose cumulative scope is admitted by a rule
# other than its own grain decision -- North Dakota and Colorado cite one rule for both, and
# Texas's scope names the allocation. An example this picked wrongly would 404, and
# `test_naked_numbers.py::test_every_documented_example_is_callable` calls every documented
# example against the API, which is what holds this to answering.
def _example_jurisdiction() -> str:
    grain = {
        str(row["jurisdiction_code"]): row["rule_id"]
        for row in SERVING_JURISDICTION_RULES
        if row["decision"] == GRAIN_DECISION
    }
    return next(
        str(row["jurisdiction_code"])
        for row in SERVING_JURISDICTION_RULES
        if row["decision"] == CUMULATIVES_SCOPE
        and grain.get(str(row["jurisdiction_code"])) != row["rule_id"]
    )


EXAMPLE_JURISDICTION = _example_jurisdiction()

# Scoped by the registration's own identity prefix, on every query that has an api10 to scope
# by. Unscoped, this route answered for North Dakota with Texas's totals, Texas's model id and
# Texas's rule, under handles that resolve (gate-tx H-2).
_ALLOCATED_TOTALS = """
select stream, sum(abs(volume)) as volume, count(*) as shares,
       count(*) filter (where allocation_class = 'allocated_after_status_change') as retired,
       sum(abs(volume)) filter (where allocation_class = 'allocated_after_status_change')
           as retired_volume,
       min(derivation_id) as derivation_id
  from marts.tx_allocated_production
 where left(api10, 2) = %(prefix)s
 group by stream
"""

_LEASE_MONTHS = """
select count(*) as lease_months,
       count(distinct (lease_key, production_month)) as lease_month_pairs
  from marts.tx_allocated_production
 where left(api10, 2) = %(prefix)s
"""

# The ledger and the crosswalk carry no api10 -- the ledger's grain is a lease-month no well
# carried, which is exactly the row an api10 predicate would drop. So the two blocks that read
# them are served only where the allocated mart holds nothing outside this registration's
# prefix: a second lease-grain jurisdiction reading these tables gets a stated absence, never
# Texas's residuals. The study is not in that set and needs no guard: it is keyed by the bed it
# was measured on and says which bed that is.
_FOREIGN_SHARES = """
select count(*) as shares from marts.tx_allocated_production
 where left(api10, 2) <> %(prefix)s
"""

# The same read `marts/cumulatives.py::allocated_prefixes` does: the named rule's own spec says
# whether the well-grain row it admits is observed or allocated. A rule-id shape test would be
# a mapping decision living in code, which R8 refuses.
_SCOPE_BASIS = """
select rule_id, spec ->> 'cumulatives_basis' as basis
  from lineage.conformance_rules where rule_id = any(%(rule_ids)s)
"""

_LEDGER = """
select stream, cause, count(*) as lease_months, sum(abs(lease_volume)) as volume,
       min(derivation_id) as derivation_id
  from marts.tx_allocation_ledger
 group by stream, cause
"""

_CROSSWALK = """
select district_no, disagreement_kind, well_count, share, derivation_id
  from marts.tx_crosswalk_residual
 order by district_no, disagreement_kind
"""

_STUDY = """
select bed_jurisdiction, model_id, error_lo, error_hi, p50, wells_scored, lease_months_scored,
       months_measured, mean_wells_per_lease, excluded_zero_zero_share,
       excluded_out_of_domain_share, derivation_id
  from marts.allocation_method_error
"""

_DEGRADED_AT = """
select (spec ->> 'unallocated_share_degraded_at')::numeric as degraded_at
  from lineage.conformance_rules where rule_id = %(rule_id)s
"""


class ValidatorBlock(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str = Field(description="Which residual this block measures.")
    outcome: str = Field(
        description=(
            "measured where the block carries figures, no_independent_truth where no control"
            " exists to compare against, or not_available where the mart has not been built."
        )
    )
    rule_id: str | None = Field(default=None, description="The decision this block reports on.")
    reasons: list[str] = Field(
        default_factory=list,
        description="Why an outcome that is not `measured` is the honest answer.",
    )


class AllocationValidators(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # No `not_a_figure`: a two-letter registry key reads as a number to nobody, and an
    # annotation the walker never sees is dead weight the gate flags rather than silences.
    jurisdiction_code: str = Field(
        description="The jurisdiction these residuals were measured over."
    )
    model_id: str | None = Field(
        default=None,
        description="The allocation model the residuals were measured against.",
        json_schema_extra={GLOSSARY_KEY: "gt_allocation_allocation_v0"},
    )
    blocks: list[ValidatorBlock] = Field(
        description="conservation, crosswalk and independent_truth, always all three."
    )
    lineage: dict[str, str] = Field(
        alias="_lineage", description="Dotted path to derivation handle (SB-07 §9.1b)."
    )
    units: dict[str, str] = Field(alias="_units", description="Dotted path to unit.")


def _decimal(value: Any) -> Decimal:
    return Decimal(0) if value is None else Decimal(value)


def _derivations(node: Any) -> set[str]:
    """Every derivation the blocks' figures cite, walked rather than listed.

    A figure this function missed would be persisted with no input behind it, which is exactly
    the untraceable number the response-output registry exists to prevent.
    """
    if isinstance(node, Figure):
        return {node.derivation}
    if isinstance(node, dict):
        return {item for value in node.values() for item in _derivations(value)}
    if isinstance(node, (list, tuple)):
        return {item for value in node for item in _derivations(value)}
    return set()


def _allocated_rule(connection: Connection, row: Any) -> str | None:
    """The jurisdiction's own scope decision, where its rule says the row it admits is a share.

    `production_grain` is registered by every jurisdiction that has a grain decision, not only
    by one that allocates, so admitting on the decision's presence answered for North Dakota,
    New Mexico and Colorado. What is asked instead is the rule's own spec.
    """
    ids = sorted(
        {
            rule
            for rule in (row.rule(CUMULATIVES_SCOPE), row.rule(GRAIN_DECISION))
            if rule is not None
        }
    )
    if not ids:
        return None
    declared = {
        item["rule_id"]: item["basis"]
        for item in rows(connection, _SCOPE_BASIS, {"rule_ids": ids})
    }
    return next((rule for rule in ids if declared.get(rule) == ALLOCATED_BASIS), None)


def _conservation(
    connection: Connection,
    degraded_at: Decimal | None,
    *,
    prefix: str,
    identity_prefix: str,
    foreign: int,
    jurisdiction: str,
    rule_id: str,
) -> dict[str, Any]:
    """V-1. The split is exact by construction, so the residual is a coverage measure.

    A non-zero difference on an allocated lease-month is a defect and the refresh raises rather
    than publishing, which is why nothing here reports one: what is served is how much volume
    had no eligible well to carry it, decomposed by cause.
    """
    if foreign:
        # The ledger's grain is a lease-month no well carried, so it holds no api10 to scope
        # by: where the allocated mart holds another jurisdiction's rows, every count below
        # would mix two registrations and `share_unallocated` would be arithmetically wrong --
        # a scoped numerator over an unscoped denominator (gate-tx RV-2).
        return {
            "name": "conservation",
            "outcome": "not_available",
            "rule_id": rule_id,
            "reasons": [
                "the allocation ledger holds another jurisdiction's rows, so no residual here"
                f" is {jurisdiction}'s"
            ],
        }
    totals = rows(connection, _ALLOCATED_TOTALS, {"prefix": identity_prefix})
    ledger = rows(connection, _LEDGER, {})
    counts = rows(connection, _LEASE_MONTHS, {"prefix": identity_prefix})[0]
    if not totals and not ledger:
        return {
            "name": "conservation",
            "outcome": "not_available",
            "rule_id": rule_id,
            "reasons": ["the allocated mart has not been built on this instance"],
        }

    derivation = next(
        (row["derivation_id"] for row in (*totals, *ledger) if row["derivation_id"]), None
    )
    allocated = sum(_decimal(row["volume"]) for row in totals)
    unallocated = sum(_decimal(row["volume"]) for row in ledger)
    retired = sum(_decimal(row["retired_volume"]) for row in totals)
    denominator = allocated + unallocated
    share_unallocated = (
        (unallocated / denominator).quantize(Decimal("0.000001")) if denominator else Decimal(0)
    )
    block: dict[str, Any] = {
        "name": "conservation",
        "outcome": "measured",
        "rule_id": rule_id,
        "reasons": [],
        "lease_months_total": figure(
            int(counts["lease_months"]),
            unit=COUNT_UNIT,
            derivation=derivation,
            selector=f"{prefix}&metric=lease_months_total",
        ),
        "lease_months_unallocated": figure(
            sum(int(row["lease_months"]) for row in ledger),
            unit=COUNT_UNIT,
            derivation=derivation,
            selector=f"{prefix}&metric=lease_months_unallocated",
        ),
        "share_unallocated": figure(
            str(share_unallocated),
            unit=SHARE_UNIT,
            derivation=derivation,
            selector=f"{prefix}&metric=share_unallocated",
        ),
        # The one eligibility error term with no date behind it, served as a bound on itself.
        "share_allocated_to_retired_wells": figure(
            str((retired / allocated).quantize(Decimal("0.000001")) if allocated else Decimal(0)),
            unit=SHARE_UNIT,
            derivation=derivation,
            selector=f"{prefix}&metric=share_allocated_to_retired_wells",
        ),
        "volume_unallocated": {
            row["stream"]: figure(
                str(_decimal(row["volume"])),
                unit="bbl" if row["stream"] == "liquid" else "mcf",
                derivation=row["derivation_id"],
                selector=f"{prefix}&metric=volume_unallocated&stream={row['stream']}",
            )
            for row in ledger
        },
        # Every cause, including the ones this run did not hit: a block listing only what it
        # found reads as a clean run rather than as a partial one.
        "decomposition": {
            cause: figure(
                sum(int(row["lease_months"]) for row in ledger if row["cause"] == cause),
                unit=COUNT_UNIT,
                derivation=derivation,
                selector=f"{prefix}&metric=unallocated_lease_months&cause={cause}",
            )
            for cause in CAUSES
        },
    }
    if degraded_at is not None:
        block["degraded_at"] = str(degraded_at)
        block["degraded"] = share_unallocated > degraded_at
    return block


def _crosswalk(connection: Connection, *, foreign: int, jurisdiction: str) -> dict[str, Any]:
    """V-2a. Two regulator-published crosswalks that agree prove nothing once averaged."""
    residuals = [] if foreign else rows(connection, _CROSSWALK, {})
    if foreign:
        return {
            "name": "crosswalk",
            "outcome": "not_available",
            "rule_id": CROSSWALK_ROLE_RULE,
            "reasons": [
                f"the crosswalk residual mart holds another jurisdiction's rows, so no"
                f" residual here is {jurisdiction}'s"
            ],
        }
    if not residuals:
        return {
            "name": "crosswalk",
            "outcome": "not_available",
            "rule_id": CROSSWALK_ROLE_RULE,
            "reasons": [
                "the crosswalk residual mart has not been built on this instance; the two"
                " crosswalks are retained unmerged and the comparison is a refresh away"
            ],
        }
    return {
        "name": "crosswalk",
        "outcome": "measured",
        "rule_id": CROSSWALK_ROLE_RULE,
        "reasons": [],
        "districts": [
            {
                "district_no": row["district_no"],
                "disagreement_kind": row["disagreement_kind"],
                "well_count": figure(
                    int(row["well_count"]),
                    unit=WELL_UNIT,
                    derivation=row["derivation_id"],
                    selector=(
                        f"district_no={row['district_no']}"
                        f"&kind={row['disagreement_kind']}&col=well_count"
                    ),
                ),
                "share": figure(
                    str(_decimal(row["share"])),
                    unit=SHARE_UNIT,
                    derivation=row["derivation_id"],
                    selector=(
                        f"district_no={row['district_no']}"
                        f"&kind={row['disagreement_kind']}&col=share"
                    ),
                ),
            }
            for row in residuals
        ],
    }


def _independent_truth(connection: Connection) -> dict[str, Any]:
    """V-2b. There is none, and Texas says so rather than serving a number that looks like one.

    A 200 with a stated outcome and named reasons, in the shape `control_unavailable` already
    takes on the modeling surface. The Montana study rides beside it as a method control on the
    same model, which is a different claim from a control on these figures.
    """
    study = rows(connection, _STUDY, {})
    block: dict[str, Any] = {
        "name": "independent_truth",
        "outcome": "no_independent_truth",
        "rule_id": ERROR_RULE,
        "reasons": [
            "the RRC publishes no per-well Texas production at any grain",
            "the 26-month W-10 and G-10 files are instantaneous tests, not monthly volumes,"
            " over a window 94 percent shorter than the history being served",
            "OG_DISTRICT_CYCLE and OG_FIELD_CYCLE are exact rollups of the same lease rows,"
            " so agreeing with them proves arithmetic rather than truth",
        ],
    }
    if study:
        row = study[0]
        block["method_control"] = {
            "bed_jurisdiction": row["bed_jurisdiction"],
            "model_id": row["model_id"],
            "transfer_outcome": "not_measured",
            "wells_scored": figure(
                int(row["wells_scored"]),
                unit=WELL_UNIT,
                derivation=row["derivation_id"],
                selector=f"bed={row['bed_jurisdiction']}&model_id={row['model_id']}"
                f"&col=wells_scored",
            ),
            "lease_months_scored": figure(
                int(row["lease_months_scored"]),
                unit=COUNT_UNIT,
                derivation=row["derivation_id"],
                selector=f"bed={row['bed_jurisdiction']}&model_id={row['model_id']}"
                f"&col=lease_months_scored",
            ),
            "months_measured": list(row["months_measured"] or ()),
            "error_lo": figure(
                str(_decimal(row["error_lo"])),
                unit=SHARE_UNIT,
                derivation=row["derivation_id"],
                selector=f"bed={row['bed_jurisdiction']}&model_id={row['model_id']}"
                f"&col=error_lo",
            ),
            "error_hi": figure(
                str(_decimal(row["error_hi"])),
                unit=SHARE_UNIT,
                derivation=row["derivation_id"],
                selector=f"bed={row['bed_jurisdiction']}&model_id={row['model_id']}"
                f"&col=error_hi",
            ),
            "p50": figure(
                str(_decimal(row["p50"])),
                unit=SHARE_UNIT,
                derivation=row["derivation_id"],
                selector=f"bed={row['bed_jurisdiction']}&model_id={row['model_id']}"
                f"&col=p50",
            ),
            "mean_wells_per_lease": figure(
                str(_decimal(row["mean_wells_per_lease"])),
                unit=WELL_UNIT,
                derivation=row["derivation_id"],
                selector=f"bed={row['bed_jurisdiction']}&model_id={row['model_id']}"
                f"&col=mean_wells_per_lease",
            ),
            "excluded_zero_zero_share": figure(
                str(_decimal(row["excluded_zero_zero_share"])),
                unit=SHARE_UNIT,
                derivation=row["derivation_id"],
                selector=f"bed={row['bed_jurisdiction']}&model_id={row['model_id']}"
                f"&col=excluded_zero_zero_share",
            ),
            "excluded_out_of_domain_share": figure(
                str(_decimal(row["excluded_out_of_domain_share"])),
                unit=SHARE_UNIT,
                derivation=row["derivation_id"],
                selector=f"bed={row['bed_jurisdiction']}&model_id={row['model_id']}"
                f"&col=excluded_out_of_domain_share",
            ),
        }
    return block


@router.get(
    "/validators/allocation",
    operation_id="get_allocation_validators",
    summary="Residuals an allocation publishes about itself",
    description=(
        "Three residual ledgers for one jurisdiction's allocation. `conservation` is the"
        " invariant: the split is exact by construction, so what is served is how much volume"
        " had no eligible well to carry it, decomposed by a closed cause vocabulary, plus the"
        " share carried by wells whose status changed without a filed date."
        " `crosswalk` is the disagreement between the two regulator-published crosswalks,"
        " which is the only measurement of identity-mapping error this system has; it reports"
        " and does not gate."
        " `independent_truth` returns `no_independent_truth` with its reasons enumerated,"
        " because the regulator publishes no per-well volume to compare against. Where a"
        " method study exists it rides in that block as a control on the model, which is a"
        " different claim from a control on these figures."
        " Every count and share is a figure with a handle."
    ),
    response_model=EnvelopeModel[AllocationValidators],
    responses=problem_responses("not_found", "validation_failed", "service_degraded"),
    # No `dataset(...)`: this is a residual ledger read by the Status page and the card, not
    # an Explore collection. Declaring it browsable would put three heterogeneous blocks into a
    # row grid that has no row.
    # The example is the jurisdiction the allocation rule is registered for, read from the
    # seed rather than written here: a jurisdiction code in a serving module is what
    # test_add_a_state.py refuses, and an example is served text like any other.
    openapi_extra={**request_example(query={"jurisdiction": EXAMPLE_JURISDICTION})},
)
def allocation_validators(
    request: Request,
    connection: Connection,
    explain: ExplainEffect,
    jurisdiction: Annotated[
        str,
        Query(
            description="Jurisdiction code, e.g. the registration whose allocation to report.",
            min_length=2,
            max_length=2,
            pattern="^[A-Z]{2}$",
        ),
    ],
) -> JSONResponse:
    registry = jurisdictions(connection)
    row = next(
        (item for item in registry if item.jurisdiction_code == jurisdiction), None
    )
    if row is None:
        raise ProblemError("not_found", detail=f"no registered jurisdiction {jurisdiction}")
    admitting = _allocated_rule(connection, row)
    if admitting is None:
        raise ProblemError(
            "not_found",
            detail=(
                f"{jurisdiction} registers no allocation decision, so it publishes no"
                " allocation residuals"
            ),
        )
    prefix = row.identity_prefix or ""
    foreign = int(rows(connection, _FOREIGN_SHARES, {"prefix": prefix})[0]["shares"])

    # The threshold the Status check reads is the rule's, so no engineer invents one: half a
    # percent of Texas volume with no well to carry it is a data question, and below that it is
    # the long tail of leases whose only well predates the crosswalk.
    declared = rows(connection, _DEGRADED_AT, {"rule_id": admitting})
    degraded_at = (
        Decimal(declared[0]["degraded_at"])
        if declared and declared[0]["degraded_at"] is not None
        else None
    )

    selector_prefix = f"jurisdiction={jurisdiction}"
    blocks = [
        _conservation(
            connection,
            degraded_at,
            prefix=selector_prefix,
            identity_prefix=prefix,
            foreign=foreign,
            jurisdiction=jurisdiction,
            rule_id=admitting,
        ),
        _crosswalk(connection, foreign=foreign, jurisdiction=jurisdiction),
        _independent_truth(connection),
    ]
    model_id = rows(
        connection,
        "select distinct allocation_model_id from marts.tx_allocated_production"
        " where left(api10, 2) = %(prefix)s limit 1",
        {"prefix": prefix},
    )
    data: dict[str, Any] = {
        "jurisdiction_code": jurisdiction,
        "model_id": model_id[0]["allocation_model_id"] if model_id else None,
        "blocks": blocks,
    }
    data = register_response_figures(
        connection,
        data,
        dataset="api.allocation_validators",
        operation_id="get_allocation_validators",
        locator=request.url.path,
        partition={"jurisdiction": jurisdiction},
        input_derivations=sorted(_derivations(blocks)),
        correlation_id=request.state.request_id,
        rule_ids=[admitting, ERROR_RULE],
    )
    return enveloped(
        request,
        data,
        links={
            "allocation_rule": f"/v1/conformance/{admitting}",
            "error_bounds_rule": f"/v1/conformance/{ERROR_RULE}",
        },
        explain=inline_for(connection, explain),
    )
