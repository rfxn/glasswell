"""Wells by a dimension: counted buckets over the well spine, with what the buckets exclude."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field
from starlette.responses import JSONResponse

from glasswell.api.deps import AsOf, Connection, ExplainEffect, Principal, rows
from glasswell.api.errors import ProblemError, problem_responses
from glasswell.api.examples import GLOSSARY_KEY, not_a_figure, request_example, semantics
from glasswell.api.provenance import register_response_figures
from glasswell.api.rate_limit import consume_rate_limit
from glasswell.api.responses import EnvelopeModel, FigureModel, enveloped, inline_for, iso
from glasswell.lineage.envelope import Figure, figure
from glasswell.lineage.selector_registry import identity_selector_term

router = APIRouter(tags=["wells"])

COUNT_UNIT = "wells"
DEFAULT_TOP = 15
MAX_TOP = 50
FACET_REQUESTS_PER_MINUTE = 60

# Each dimension is a column on the spine and a filter `/v1/wells` already accepts, so a bucket
# is a link the collection can answer rather than a number with nowhere to go. `completion_year`
# is the one derived value: the column is a date and a bucket per day is not a dimension.
#
# Every column is wrapped in `nullif(..., '')`: a source that reports an empty string is
# reporting no value, and letting "" through would mint a bucket with no name, ranked among the
# real ones, whose selector is unaddressable (the grammar admits no empty value). It belongs in
# the absence bucket, which is what cr_tx_operator_absence_1 and cr_mt_operator_absence_1 both
# already say about a blank operator.
DIMENSIONS: dict[str, dict[str, str]] = {
    "operator": {
        "column": "nullif(w.operator_name_reported, '')",
        "filter": "operator",
        "title": "current operator, as the source reported it",
    },
    "county": {
        "column": "nullif(w.county_code_at_permit, '')",
        "filter": "county",
        "title": "county code recorded at permit",
    },
    "status": {
        "column": "nullif(w.status_canonical, '')",
        "filter": "status",
        "title": "canonical well status",
    },
    "well_type": {
        "column": "nullif(w.well_type_reported, '')",
        "filter": "well_type",
        "title": "well type code, verbatim from the source",
    },
    "completion_year": {
        "column": "to_char(w.completion_date, 'YYYY')",
        "filter": "",
        "title": "year of the reported completion date",
    },
}
Dimension = Literal["operator", "county", "status", "well_type", "completion_year"]

# The states the spine actually carries rows for is a fact about the load, not about this
# module, so the enum is not pinned here — `_require_state` reads it from the data and names
# what it found. Montana and New Mexico prove why: MT holds 40,626 wells whose GIS layer has
# not been published, and NM's promotion is gated, so a hard-coded four-state enum would be
# wrong in both directions within one release.
STATE_PATTERN = r"^\d{2}$"

# The map's layer panel renamed every state row to `Noun (Full state name)` when it grew a
# `Wells` parent, so the name is served rather than mapped again in the client: two spellings of
# "North Dakota" 200 px apart is the drift that convention was introduced to end. Keyed by API
# state code, which is not FIPS — 25 is Montana here, not Massachusetts.
STATE_NAMES = {"25": "Montana", "30": "New Mexico", "33": "North Dakota", "42": "Texas"}

# R8: what an absent value means is a per-source decision with a rationale and a date, never an
# inference this module makes. A state/dimension pair absent from this map has no registered
# rule, and the response says so rather than implying the absence is understood.
ABSENCE_RULES = {
    ("42", "operator"): "cr_tx_operator_absence_1",
    ("25", "operator"): "cr_mt_operator_absence_1",
}

# The name a bucket is given when the dimension has no value. It is never a value in the
# ranking: on the 2026-08-30 Texas load it would outrank all 9,369 real operators.
ABSENCE_LABEL = "not reported"

_VALUE_SORTS = {
    ("count", "desc"): "wells desc, value asc",
    ("count", "asc"): "wells asc, value asc",
    ("value", "desc"): "value desc",
    ("value", "asc"): "value asc",
}

# The whole population, deduped to one row per well. Referenced once on purpose: `bucketed` is
# what the four summary arms read, and a second reference to `scoped` would materialise 359,421
# rows to recount what 9,370 already answer.
_SCOPED_LATEST = """
    select distinct on (w.api10) w.api10, {column} as value, w.derivation_id
      from canonical.wells w
     where w.state_code = %(state)s
     order by w.api10, w.effective_from desc, w.created_at desc
"""

# The knowledge-time arm. The two joins are dropped from the arm above rather than left with a
# null-guarded predicate: both columns are `not null` foreign keys, so with no `as_of` the joins
# filter nothing and cost two probes per spine row.
_SCOPED_AS_OF = """
    select distinct on (w.api10) w.api10, {column} as value, w.derivation_id
      from canonical.wells w
      join lineage.manifests m on m.manifest_id = w.source_manifest_id
      join lineage.derivations d on d.derivation_id = w.derivation_id
     where w.state_code = %(state)s
       and w.effective_from <= %(as_of)s::date
       and m.fetch_vintage <= %(as_of)s::date
       and (d.created_vintage is null or d.created_vintage <= %(as_of)s::date)
     order by w.api10, w.effective_from desc, w.created_at desc
"""

# Five arms over one aggregate, so the served list and the three claims about what it leaves out
# are counted in the same pass and cannot disagree. `scope` counts the null bucket in its total
# and excludes it from `values`, which is what makes buckets + remainder + absence == wells.
_FACETS = """
with scoped as ({scoped}),
     bucketed as (
    select value, count(*)::bigint as wells, max(derivation_id) as derivation_id
      from scoped
     group by value),
     matched as (
    select * from bucketed
     where value is not null
       and (%(q)s::text is null or value ilike '%%' || %(q)s || '%%')),
     ranked as (
    select *, row_number() over (order by {order}) as rank from matched)
select 'bucket'::text as kind, value, wells, derivation_id, null::bigint as values, rank
  from ranked
 where rank <= %(top)s
union all
select 'remainder', null, coalesce(sum(wells), 0), max(derivation_id), count(*)::bigint, null
  from ranked
 where rank > %(top)s
union all
select 'absence', null, wells, derivation_id, null::bigint, null
  from bucketed
 where value is null
union all
select 'matched', null, coalesce(sum(wells), 0), max(derivation_id), count(*)::bigint, null
  from matched
union all
select 'scope', null, coalesce(sum(wells), 0), max(derivation_id),
       count(*) filter (where value is not null)::bigint, null
  from bucketed
"""

_STATES = """
select state_code, count(distinct api10)::bigint as wells
  from canonical.wells
 where state_code is not null
 group by state_code
 order by state_code
"""


class FacetBucket(BaseModel):
    """One value of the dimension and how many current wells carry it."""

    value: str = Field(description="The value as the source reported it; never normalised here.")
    wells: FigureModel = Field(description="Wells carrying this value, in the scoped state.")
    links: dict[str, str] = Field(
        description=(
            "`wells` narrows the collection to this bucket, in this state. Absent where the"
            " collection accepts no filter for the dimension, rather than published as a link"
            " that narrows to something else. Note that `operator` is matched by the"
            " collection as a case-insensitive substring while this bucket is an exact group,"
            " so an operator name that contains a shorter one returns the longer name's rows"
            " too; the count here is the exact group and is the figure."
        )
    )


class FacetRemainder(BaseModel):
    """What the served list leaves out, counted rather than implied."""

    values: int = Field(
        description="Distinct values ranked below the cut.",
        json_schema_extra=not_a_figure(
            "Cardinality of the value list below the served cut. The wells those values hold"
            " is the figure beside it and carries a handle."
        ),
    )
    wells: FigureModel = Field(description="Wells held by every value below the cut, summed.")
    detail: str = Field(description="What the remainder is, in words, for a reader who skims.")


class FacetAbsence(BaseModel):
    """Wells the dimension has no value for, as their own named bucket."""

    label: str = Field(description="What the bucket is called wherever it is shown.")
    detail: str = Field(description="What an absent value means on this source.")
    rule_id: str | None = Field(
        description="The conformance rule that decided it, or null where none is registered.",
        json_schema_extra={GLOSSARY_KEY: "gt_conformance_rule"},
    )
    wells: FigureModel = Field(description="Wells with no value for this dimension.")
    links: dict[str, str] = Field(description="`rule` resolves the decision, when there is one.")


class FacetState(BaseModel):
    """A state this operation knows about, and whether the spine currently holds wells for it."""

    code: str = Field(
        description="API state code.",
        json_schema_extra=not_a_figure(
            "API state code carried as reported; an identifier, not a quantity."
        ),
    )
    name: str = Field(description="The state's name, in the `Noun (Full state name)` convention.")
    loaded: bool = Field(
        description="False where the spine holds no well for it, which is a gated or unrun"
        " ingest and not an empty facet list."
    )


class WellFacets(BaseModel):
    """SB-04 §2.2 data for one dimension of one state."""

    state: str = Field(
        description="API state code the counts are scoped to.",
        json_schema_extra=not_a_figure(
            "API state code carried as reported; an identifier, not a quantity."
        ),
    )
    state_name: str = Field(
        description="The state's name, so a client renders `Wells (North Dakota)` without"
        " carrying a second copy of the mapping."
    )
    dimension: str = Field(description="Which dimension the wells are counted by.")
    dimension_title: str = Field(description="What the dimension means, in one line.")
    sort: str = Field(description="Echo of the ranking asked for.")
    order: str = Field(description="Echo of the direction asked for.")
    q: str | None = Field(description="Echo of the search, or null when the whole state ranked.")
    top: int = Field(
        description="The cut asked for. `buckets` is at most this long.",
        json_schema_extra=not_a_figure(
            "Echo of the requested page cut; it counts nothing in the data. Served because a"
            " reader must be able to see the list is a cut of fifteen without counting the"
            " array."
        ),
    )
    distinct_values: int = Field(
        description="Distinct non-absent values the scope holds, before the cut.",
        json_schema_extra=not_a_figure(
            "Cardinality of a value list, not a measured or modelled petroleum figure. How"
            " many operators exist is a fact about the vocabulary; how many wells they hold"
            " is the figure beside it, and that one carries a handle."
        ),
    )
    caption: str = Field(
        description="What this list is, in one sentence, including what it is a cut of. Served"
        " rather than composed by the client so the count and the sentence cannot disagree."
    )
    buckets: list[FacetBucket] = Field(description="The leading values, ranked as asked.")
    remainder: FacetRemainder | None = Field(
        description="Absent when the list is complete; present whenever anything was cut."
    )
    absence: FacetAbsence | None = Field(
        description="Absent when every well in scope carries a value."
    )
    wells: FigureModel | None = Field(
        description="Every current well in the scoped state, absent when the state holds none."
    )
    matched_wells: FigureModel | None = Field(
        description="Wells under the search, absent when no search was asked for."
    )
    states: list[FacetState] = Field(
        description="Every state this operation knows, loaded or not, so a picker can offer"
        " them all and say which one has nothing behind it yet."
    )
    rules: list[str] = Field(
        description="Every conformance rule these counts cite; each one is linked.",
        json_schema_extra={GLOSSARY_KEY: "gt_conformance_rule"},
    )


def _require_state(connection: Any, state: str) -> list[dict[str, Any]]:
    """The scope is required and refused when empty, because a facet cannot say so afterwards.

    A state with no rows would otherwise answer 200 with an empty list, which reads as "this
    operator list is empty" rather than "this state is not loaded" — and Montana and New Mexico
    make that distinction live rather than theoretical.
    """
    found = rows(connection, _STATES)
    if any(row["state_code"] == state for row in found):
        return found
    carried = ", ".join(
        f"{row['state_code']} — {STATE_NAMES.get(row['state_code'], 'unnamed')}"
        f" ({row['wells']:,} wells)"
        for row in found
    )
    raise ProblemError(
        "validation_failed",
        detail=(
            f"the spine carries no well in state {state}, so there is nothing to count by."
            f" Loaded states: {carried or 'none'}"
        ),
        # The same list the success path serves, on the refusal, because a refusal that does
        # not say what you *can* ask for is a dead end: the panel's state picker is rebuilt
        # from this, and without it a link to a gated state renders a control with nothing in
        # it and no way back except editing the URL.
        extra={"states": _states(found)},
        errors=[
            {
                "pointer": "/query/state",
                "code": "state_not_loaded",
                "detail": (
                    "A state whose ingest has not run is not an empty facet list; it is a"
                    " different question, and this operation refuses rather than answer it as"
                    " though the operators were counted and there were none."
                ),
            }
        ],
    )


def _partition_term(name: str, value: str) -> tuple[str, str]:
    """A partition entry is rendered as a selector, so it obeys the selector charset.

    `register_response_figures` formats the partition through `format_selector`, which refuses a
    space and refuses an empty value — so a search for "chevron usa" cannot be written verbatim.
    Encoding it through the same helper the figure selectors use keeps one grammar rather than
    two, and keeps two different searches in two different partitions.
    """
    key, _, encoded = identity_selector_term(name, value).partition("=")
    return key, encoded


def _states(loaded: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every known state, with the ones holding no wells said rather than omitted.

    A picker built from the loaded set alone cannot distinguish "New Mexico has no operators"
    from "New Mexico is not promoted yet", and the second is the true one today.
    """
    carrying = {row["state_code"] for row in loaded}
    codes = sorted(set(STATE_NAMES) | carrying)
    return [
        {"code": code, "name": STATE_NAMES.get(code, f"state {code}"), "loaded": code in carrying}
        for code in codes
    ]


def _selector(
    dimension: str, state: str, q: str | None, part: str, value: str | None = None
) -> str:
    """One selector grammar for every figure: what was counted, of what, under which search."""
    terms = [f"col={part}", f"dimension={dimension}", f"state={state}"]
    if value is not None:
        terms.append(identity_selector_term("value", value))
    if q is not None:
        terms.append(identity_selector_term("q", q))
    return "&".join(terms)


def _figure(row: dict[str, Any] | None, selector: str) -> Figure | None:
    """Absent, not zero: a bucket the scope does not contain has no count and no derivation."""
    if row is None or row["derivation_id"] is None:
        return None
    return figure(
        str(row["wells"]), unit=COUNT_UNIT, derivation=row["derivation_id"], selector=selector
    )


def _absence(
    row: dict[str, Any] | None, *, state: str, dimension: str, q: str | None
) -> dict[str, Any] | None:
    """The named bucket for wells the dimension has no value for.

    It is built outside the ranking and outside the search on purpose. A search over operator
    names cannot match a well that has no operator name, so filtering the absence bucket by `q`
    would make 70,039 Texas wells vanish the moment a reader typed a letter — the population
    would silently change under a control that says it only narrows a list.
    """
    if row is None or row["wells"] == 0:
        return None
    rule = ABSENCE_RULES.get((state, dimension))
    counted = _figure(row, _selector(dimension, state, q, "absent_wells"))
    if counted is None:
        return None
    detail = (
        f"These wells carry no {dimension.replace('_', ' ')}. The decision that this is an"
        " absence rather than an unknown is registered, with its evidence and its date."
        if rule
        else (
            f"These wells carry no {dimension.replace('_', ' ')}. No conformance rule states"
            " what that absence means on this source, so this bucket counts them and claims"
            " nothing further about them (R8)."
        )
    )
    return {
        "label": ABSENCE_LABEL,
        "detail": detail,
        "rule_id": rule,
        "wells": counted,
        "links": {"rule": f"/v1/conformance/{rule}"} if rule else {},
    }


def _remainder(
    row: dict[str, Any] | None, *, state: str, dimension: str, q: str | None, top: int
) -> dict[str, Any] | None:
    if row is None or row["values"] in (None, 0):
        return None
    counted = _figure(row, _selector(dimension, state, q, "remainder_wells"))
    if counted is None:
        return None
    noun = dimension.replace("_", " ")
    scope = f" matching {q!r}" if q is not None else ""
    return {
        "values": int(row["values"]),
        "wells": counted,
        "detail": (
            f"{int(row['values']):,} further {noun} values{scope} hold {int(row['wells']):,}"
            f" wells between them, and are not in this list of {top}."
        ),
    }


def _caption(
    *, dimension: str, state: str, shown: int, distinct: int, q: str | None, sort: str
) -> str:
    """The one sentence that has to be true: what is on screen, and what it is a cut of."""
    noun = dimension.replace("_", " ")
    name = STATE_NAMES.get(state, f"state {state}")
    if distinct == 0:
        return (
            f"No {noun} in {name} matches {q!r}. The search ran over all of them, so this is"
            " the whole answer."
            if q is not None
            else f"No well in {name} carries a {noun}."
        )
    matching = f" matching {q!r}" if q is not None else ""
    of = (
        f"{distinct:,} {noun} value{'s' if distinct != 1 else ''}{matching} in {name}"
        if q is None
        else f"{distinct:,} {noun} values{matching} in {name}"
    )
    if shown >= distinct:
        return f"All {of}, ranked by {'well count' if sort == 'count' else 'value'}."
    return (
        f"The {shown:,} {noun} value{'s' if shown != 1 else ''} with the most wells, of {of}."
        if sort == "count"
        else f"{shown:,} of {of}, ranked by value."
    )


def _bucket_link(dimension: str, value: str, state: str) -> dict[str, str]:
    """A bucket the collection cannot reproduce gets no link rather than a link that lies."""
    name = DIMENSIONS[dimension]["filter"]
    if not name:
        return {}
    return {"wells": f"/v1/wells?{name}={value}&state={state}"}


def _warnings(
    *, state: str, dimension: str, absence: dict[str, Any] | None, truncated: bool, q: str | None
) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    if absence is not None and absence["rule_id"] is None:
        warnings.append(
            {
                "code": "absence_unregistered",
                "detail": (
                    f"State {state} has wells with no {dimension.replace('_', ' ')} and no"
                    " registered rule saying what that absence means. The count is the"
                    " promoted data; the decision behind it is not citable until it is a"
                    " conformance row (R8)."
                ),
                "pointer": "/absence",
            }
        )
    if truncated:
        warnings.append(
            {
                "code": "list_truncated",
                "detail": (
                    "This list is a ranked cut, not the population. `remainder` counts every"
                    " value below it and the wells they hold; `distinct_values` is how many"
                    " there are in total."
                ),
                "pointer": "/buckets",
            }
        )
    if q is not None:
        warnings.append(
            {
                "code": "search_scopes_the_ranking",
                "detail": (
                    "The search ran over every value in the state before the cut, so these are"
                    " the leading matches and not the matches within a page. `absence` is"
                    " outside it: a well with no value matches no search text."
                ),
                "pointer": "/buckets",
            }
        )
    return warnings


@router.get(
    "/wells/facets",
    operation_id="get_well_facets",
    summary="Wells by a dimension, counted",
    description=(
        "How many current wells carry each value of one dimension, ranked, for one state. This"
        " is the question a screening pass opens with — who operates here, what is in this"
        " county, how old is the completion population — asked of the spine rather than of a"
        " page of it. The population is every current well the state has promoted, so the"
        " ranking does not move with the viewport, with paging, or with which rows a grid has"
        " fetched."
        " Scope is one state and is required. Operator names arrive per source and"
        " `lineage.operator_aliases` carries no row for any state served here, so the same"
        " company spelled two ways in two jurisdictions is two values; summing them across a"
        " border would be an aliasing decision no conformance rule has made, and this operation"
        " declines to make it silently (R8)."
        " Three things about what the list is not are counted rather than implied: `remainder`"
        " holds every value below the cut and the wells they carry, `distinct_values` is how"
        " many values the state holds in total, and `absence` is its own named bucket for wells"
        " the dimension has no value for. The absence bucket never enters the ranking — on the"
        " current Texas load it would outrank all 9,369 operators — and never enters the"
        " search, because a well with no name matches no name. `buckets` + `remainder` +"
        " `absence` sum to `wells`, always."
        " Every count is a figure with a derivation handle, so a bucket resolves at /v1/explain"
        " to the government file its wells were promoted from. Because each distinct dimension,"
        " search and cut persists exact response evidence, this operation is capped at 60"
        " requests per principal per UTC minute."
        " It does not return the wells themselves — each bucket links to /v1/wells, which does."
    ),
    response_model=EnvelopeModel[WellFacets],
    openapi_extra={
        **request_example(query={"state": "33", "by": "operator", "top": 15}),
        **semantics(
            state={
                "glossary": "gt_api_10_api_12_api_14",
                "so": (
                    "The API state code, the first two digits of every API-10 in the bucket."
                    " Required, and refused when the spine holds no well for it: a state whose"
                    " ingest has not run is a different answer from a state with no operators,"
                    " and only one of them is worth serving as an empty list."
                ),
            },
            by={
                "glossary": "gt_conformance_rule",
                "so": (
                    "Which column the wells are grouped by. Each one is also a filter"
                    " /v1/wells accepts, so every bucket links to the rows behind it."
                ),
            },
            q={
                "glossary": "gt_conformance_rule",
                "so": (
                    "Case-insensitive substring, applied to every value in the state before"
                    " the ranking — not to the served page. Searching 9,369 operators for the"
                    " one you mean is the case this exists for, so it cannot be a filter over"
                    " fifteen rows."
                ),
            },
            as_of={
                "glossary": "gt_knowledge_time",
                "so": (
                    "Counts the wells as they were described on that knowledge date. A status"
                    " or operator restatement appends a row, so an earlier cut ranks the"
                    " earlier operator and the totals move with it."
                ),
            },
            explain={
                "glossary": "gt_derivation_handle",
                "so": (
                    "Inlines the chain behind every bucket count, the remainder and the"
                    " absence bucket under `_explain`. A list of fifteen is sixteen separate"
                    " /v1/explain calls by hand."
                ),
            },
            explain_depth={
                "glossary": "gt_derivation_handle",
                "so": (
                    "A bucket resolves to the promotion that wrote its wells and the file they"
                    " came from, so three levels reaches the manifest."
                ),
            },
        ),
    },
    responses=problem_responses("validation_failed", "service_degraded"),
)
def get_well_facets(
    request: Request,
    connection: Connection,
    principal: Principal,
    state: Annotated[
        str,
        Query(
            description="API state code, e.g. 33 for North Dakota. Required.",
            pattern=STATE_PATTERN,
        ),
    ],
    by: Annotated[Dimension, Query(description="The dimension to count wells by.")],
    explain: ExplainEffect,
    top: Annotated[
        int, Query(ge=1, le=MAX_TOP, description=f"Values to serve, {DEFAULT_TOP} by default.")
    ] = DEFAULT_TOP,
    q: Annotated[
        str | None, Query(description="Case-insensitive substring of the value.")
    ] = None,
    sort: Annotated[
        Literal["count", "value"], Query(description="Rank by well count or by value.")
    ] = "count",
    order: Annotated[Literal["desc", "asc"], Query(description="Ranking direction.")] = "desc",
    as_of: AsOf = None,
) -> JSONResponse:
    loaded = _require_state(connection, state)
    consume_rate_limit(
        connection, principal, operation="get_well_facets", limit=FACET_REQUESTS_PER_MINUTE
    )
    scoped = (_SCOPED_AS_OF if as_of is not None else _SCOPED_LATEST).format(
        column=DIMENSIONS[by]["column"]
    )
    statement = _FACETS.format(scoped=scoped, order=_VALUE_SORTS[(sort, order)])
    found = rows(
        connection, statement, {"state": state, "as_of": as_of, "q": q, "top": top}
    )
    by_kind: dict[str, list[dict[str, Any]]] = {}
    for row in found:
        by_kind.setdefault(row["kind"], []).append(row)
    one = {kind: group[0] for kind, group in by_kind.items() if kind != "bucket"}
    listed = sorted(by_kind.get("bucket", []), key=lambda row: row["rank"])

    absence = _absence(one.get("absence"), state=state, dimension=by, q=q)
    remainder = _remainder(one.get("remainder"), state=state, dimension=by, q=q, top=top)
    scope = one.get("scope")
    data: dict[str, Any] = {
        "state": state,
        "state_name": STATE_NAMES.get(state, f"state {state}"),
        "dimension": by,
        "dimension_title": DIMENSIONS[by]["title"],
        "sort": sort,
        "order": order,
        "q": q,
        "top": top,
        "distinct_values": int(scope["values"]) if scope and scope["values"] else 0,
        "caption": _caption(
            dimension=by,
            state=state,
            shown=len(listed),
            distinct=(
                int(one["matched"]["values"])
                if q is not None and one.get("matched") and one["matched"]["values"]
                else (int(scope["values"]) if scope and scope["values"] else 0)
            ),
            q=q,
            sort=sort,
        ),
        "buckets": [
            {
                "value": row["value"],
                "wells": _figure(row, _selector(by, state, q, "wells", row["value"])),
                "links": _bucket_link(by, row["value"], state),
            }
            for row in listed
        ],
        "remainder": remainder,
        "absence": absence,
        "wells": _figure(scope, _selector(by, state, None, "scope_wells")),
        "matched_wells": (
            _figure(one.get("matched"), _selector(by, state, q, "matched_wells"))
            if q is not None
            else None
        ),
        "states": _states(loaded),
        "rules": sorted({absence["rule_id"]} if absence and absence["rule_id"] else set()),
    }
    data = register_response_figures(
        connection,
        data,
        dataset="api.well_facets",
        operation_id="get_well_facets",
        locator=request.url.path,
        partition=dict(
            [
                ("state", state),
                ("dimension", by),
                ("top", str(top)),
                ("sort", f"{sort}:{order}"),
                ("as_of", iso(as_of) or "latest"),
            ]
            # Omitted rather than emptied when absent: no search and a search for nothing are
            # the same request, and an empty selector value is refused by the grammar.
            + ([_partition_term("q", q)] if q is not None else [])
        ),
        input_derivations=sorted(
            {row["derivation_id"] for row in found if row["derivation_id"] is not None}
        ),
        correlation_id=request.state.request_id,
        rule_ids=data["rules"],
    )
    return enveloped(
        request,
        data,
        as_of=as_of,
        as_of_requested=iso(as_of) or "latest",
        labels={"/rules": "gt_conformance_rule", "/absence/rule_id": "gt_conformance_rule"},
        warnings=_warnings(
            state=state,
            dimension=by,
            absence=absence,
            truncated=remainder is not None,
            q=q,
        ),
        links={rule: f"/v1/conformance/{rule}" for rule in data["rules"]},
        explain=inline_for(connection, explain),
    )
