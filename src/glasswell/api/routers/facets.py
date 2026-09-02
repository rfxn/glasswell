"""Wells by a dimension: counted buckets over the well spine, with what the buckets exclude."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Annotated, Any, Literal, NoReturn
from urllib.parse import urlencode

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field
from starlette.responses import JSONResponse

from glasswell.api.deps import AsOf, Connection, ExplainEffect, Principal, jurisdictions, rows
from glasswell.api.errors import ProblemError, problem_responses
from glasswell.api.examples import GLOSSARY_KEY, not_a_figure, request_example, semantics
from glasswell.api.provenance import register_response_figures
from glasswell.api.rate_limit import consume_rate_limit
from glasswell.api.responses import EnvelopeModel, FigureModel, enveloped, inline_for, iso
from glasswell.lineage.envelope import Figure, figure
from glasswell.lineage.jurisdictions import JurisdictionRegistry
from glasswell.lineage.selector_registry import identity_selector_term
from glasswell.status_resolution import resolved_status, resolver_join

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
    # The only dimension that joins: New Mexico's class is resolved at read time, so a bucket
    # read off the promoted column alone would count 141,778 wells as unmapped while the map
    # draws them classed (cr_nm_wellhistory_status_vocab_2).
    "status": {
        "column": f"nullif({resolved_status('w')}, '')",
        "join": resolver_join("w"),
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
# module, so the enum is not pinned here — `_require_states` reads it from the data and names
# what it found. Montana and New Mexico prove why: MT holds 40,626 wells whose GIS layer has
# not been published, and NM's promotion is gated, so a hard-coded four-state enum would be
# wrong in both directions within one release.
# The scope is a set. One `state` term may carry a comma list and the term may repeat, so the
# grammar below is one term's, not the whole set's; `all` is the registry read at request time,
# which is what lets a fifth jurisdiction join the answer without an edit here.
ALL_JURISDICTIONS = "all"
STATE_SET_PATTERN = rf"^(?:{ALL_JURISDICTIONS}|\d{{2}}(?:,\d{{2}})*)$"
# The grammar belongs to the term, not to the list: a `pattern` on the array would be applied
# to the array itself, which pydantic refuses outright.
StateTerm = Annotated[str, Field(pattern=STATE_SET_PATTERN)]

# What a jurisdiction does with the dimension being counted, per R8. `absent_by_rule` is the
# one that moves wells: they leave the shared "not reported" bucket, because an absence a rule
# explains and an absence nothing explains are two populations and one bucket cannot be both.
CARRIED = "carried"
ABSENT_BY_RULE = "absent_by_rule"
ABSENT_UNREGISTERED = "absent_unregistered"
# A jurisdiction that contributes no well to the scope has exercised no absence rule: the cause
# is the knowledge cut the reader asked for, not a decision anybody registered. `all` resolves
# against what the spine carries today and the counts are taken as of the asked date, so any
# `as_of` before a jurisdiction's promotion produces this.
NO_WELLS_IN_SCOPE = "no_wells_in_scope"

# The map's layer panel renamed every state row to `Noun (Full state name)` when it grew a
# `Wells` parent, so the name is served rather than mapped again in the client: two spellings of
# "North Dakota" 200 px apart is the drift that convention was introduced to end. It comes from
# the registration the API state code resolves to, which is not FIPS — 25 is Montana here.
#
# R8: what an absent value means is a per-source decision with a rationale and a date, never an
# inference this module makes. It is a jurisdiction_rules decision at (jurisdiction, dimension)
# grain, so a dimension with no registered rule says so rather than implying the absence is
# understood.
ABSENCE_DECISION = "absence"


def _state_name(registry: JurisdictionRegistry, state: str) -> str:
    """An unregistered code is shown as itself rather than guessed at."""
    return registry.name_for(state) or f"state {state}"


def _absence_rule(registry: JurisdictionRegistry, state: str, dimension: str) -> str | None:
    return registry.rule_for(state, f"{ABSENCE_DECISION}:{dimension}")

# The name a bucket is given when the dimension has no value. It is never a value in the
# ranking: on the 2026-08-30 Texas load it would outrank all 9,369 real operators.
ABSENCE_LABEL = "not reported"

_VALUE_SORTS = {
    ("count", "desc"): "wells desc, value asc",
    ("count", "asc"): "wells asc, value asc",
    ("value", "desc"): "value desc",
    ("value", "asc"): "value asc",
}

# The whole population, deduped to one row per well. Referenced once on purpose: `per_state` is
# what every other arm reads, and a second reference to `scoped` would materialise 359,421 rows
# to recount what 9,370 already answer.
#
# Deduped per (state_code, api10) rather than per api10 alone: an API-10's leading pair is its
# jurisdiction's registered identity_prefix, so the two partitions are the same one, and only
# this order matches wells_facet_dimensions_idx. Over a set the api10-only form cannot use the
# index at all -- measured on the deployed 585,864 wells at 279,288 buffers / 1,031 ms against
# 12,780 / 592 ms index-only (web/PERF.md §7).
_SCOPED_LATEST = """
    select distinct on (w.state_code, w.api10)
           w.state_code, w.api10, {column} as value, w.derivation_id
      from canonical.wells w
      {join}
     where w.state_code = any(%(states)s)
     order by w.state_code, w.api10, w.effective_from desc, w.created_at desc
"""

# The knowledge-time arm. The two joins are dropped from the arm above rather than left with a
# null-guarded predicate: both columns are `not null` foreign keys, so with no `as_of` the joins
# filter nothing and cost two probes per spine row.
_SCOPED_AS_OF = """
    select distinct on (w.state_code, w.api10)
           w.state_code, w.api10, {column} as value, w.derivation_id
      from canonical.wells w
      join lineage.manifests m on m.manifest_id = w.source_manifest_id
      join lineage.derivations d on d.derivation_id = w.derivation_id
      {join}
     where w.state_code = any(%(states)s)
       and w.effective_from <= %(as_of)s::date
       and m.fetch_vintage <= %(as_of)s::date
       and (d.created_vintage is null or d.created_vintage <= %(as_of)s::date)
     order by w.state_code, w.api10, w.effective_from desc, w.created_at desc
"""

# Five arms over one aggregate, so the served list and the claims about what it leaves out are
# counted in the same pass and cannot disagree. `scope` counts the null bucket in its total and
# excludes it from `values`, which is what makes buckets + remainder + absence == wells with no
# `q` in force; under one the ranked arms read `matched` and only `scope` still reads the whole
# scope, so buckets + remainder == matched instead.
#
# `per_state` is the grain the multi-jurisdiction arms need and the only one referenced twice:
# it is (jurisdiction x value), thousands of rows rather than the hundreds of thousands `scoped`
# holds, so materialising it costs one small hash rather than a second pass of the spine. The
# `jurisdiction` arm is what lets the response name the set it counted over, say which
# jurisdictions carry the dimension, and carry a derivation from every one of them.
_FACETS = """
with scoped as ({scoped}),
     per_state as (
    select state_code, value, count(*)::bigint as wells, max(derivation_id) as derivation_id
      from scoped
     group by state_code, value),
     bucketed as (
    select value, sum(wells)::bigint as wells, max(derivation_id) as derivation_id
      from per_state
     group by value),
     matched as (
    select * from bucketed
     where value is not null
       and (%(q)s::text is null or value ilike '%%' || %(q)s || '%%')),
     ranked as (
    select *, row_number() over (order by {order}) as rank from matched)
select 'bucket'::text as kind, value, wells, derivation_id, null::bigint as values, rank,
       null::bigint as absent
  from ranked
 where rank <= %(top)s
union all
select 'remainder', null, coalesce(sum(wells), 0), max(derivation_id), count(*)::bigint,
       null, null
  from ranked
 where rank > %(top)s
union all
select 'matched', null, coalesce(sum(wells), 0), max(derivation_id), count(*)::bigint,
       null, null
  from matched
union all
select 'scope', null, coalesce(sum(wells), 0), max(derivation_id),
       count(*) filter (where value is not null)::bigint, null, null
  from bucketed
union all
select 'jurisdiction', state_code, sum(wells)::bigint, max(derivation_id),
       count(*) filter (where value is not null)::bigint, null,
       coalesce(sum(wells) filter (where value is null), 0)::bigint
  from per_state
 group by state_code
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


class FacetJurisdiction(BaseModel):
    """One jurisdiction the counts were taken over, and what it does with this dimension."""

    code: str = Field(
        description="API state code.",
        json_schema_extra=not_a_figure(
            "API state code carried as reported; an identifier, not a quantity."
        ),
    )
    name: str = Field(description="The state's name, in the `Noun (Full state name)` convention.")
    wells: FigureModel | None = Field(
        description="Current wells this jurisdiction contributes to the scope; absent where"
        " it contributes none."
    )
    dimension: str = Field(
        description=(
            "`carried` where the jurisdiction holds at least one value of this dimension."
            " `absent_by_rule` where it holds none and a registered rule says what that"
            " absence means -- those wells are counted here and are NOT in the `absence`"
            " bucket, because an explained absence and an unexplained one are two"
            " populations. `absent_unregistered` where it holds none and no rule states why,"
            " which is disclosed rather than answered as either of the other two (R8)."
            " `no_wells_in_scope` where it contributes no well at all, which under an `as_of`"
            " before its promotion is a fact about the knowledge cut and not about the"
            " jurisdiction; `rule_id` may still name a registered decision, but no absence"
            " has been exercised and none is claimed."
        ),
        json_schema_extra={GLOSSARY_KEY: "gt_conformance_rule"},
    )
    rule_id: str | None = Field(
        description="The conformance rule registered for this jurisdiction's absence on this"
        " dimension, or null where none is.",
        json_schema_extra={GLOSSARY_KEY: "gt_conformance_rule"},
    )


class WellFacets(BaseModel):
    """SB-04 §2.2 data for one dimension of one set of jurisdictions."""

    state: str = Field(
        description="Echo of the scope asked for: `all`, or the normalised comma list of API"
        " state codes the counts are scoped to.",
        json_schema_extra=not_a_figure(
            "API state code carried as reported; an identifier, not a quantity."
        ),
    )
    state_name: str = Field(
        description="The scope's name, so a client renders `Wells (North Dakota)` without"
        " carrying a second copy of the mapping. A set is named as a list, in code order."
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
        description="Absent when every well in scope carries a value. It counts only the"
        " jurisdictions that carry the dimension: one whose absence a rule explains is named"
        " in `jurisdictions` instead."
    )
    wells: FigureModel | None = Field(
        description="Every current well in the scope, absent when it holds none."
    )
    matched_wells: FigureModel | None = Field(
        description="Wells under the search, absent when no search was asked for. `buckets`"
        " + `remainder` sum to it, because both are inside the search and `absence` is not."
    )
    jurisdictions: list[FacetJurisdiction] = Field(
        description="The set the counts were taken over, in code order, and what each one"
        " does with this dimension. A combined bucket is only readable beside this: it says"
        " which jurisdictions are in the number and which are outside the absence bucket."
    )
    states: list[FacetState] = Field(
        description="Every state this operation knows, loaded or not, so a picker can offer"
        " them all and say which one has nothing behind it yet."
    )
    rules: list[str] = Field(
        description="Every conformance rule these counts cite; each one is linked.",
        json_schema_extra={GLOSSARY_KEY: "gt_conformance_rule"},
    )


def state_set(values: Sequence[str]) -> tuple[str, ...] | None:
    """The jurisdictions a request asked for, normalised, or None for every registered one.

    Shared with `/v1/wells` so a facet bucket and the link it publishes cannot read the same
    query string as two different populations. Repetition and comma lists are one grammar;
    order and duplicates are not part of the question.
    """
    codes: list[str] = []
    every = False
    for value in values:
        # `term`, not `token`: this module sits under the auth path that
        # test_constant_time.py sweeps, and that gate reads a name in SECRET_NAMES
        # compared with == as a credential comparison, whoever wrote it.
        for term in value.split(","):
            if term == ALL_JURISDICTIONS:
                every = True
            elif term:
                codes.append(term)
    if every and codes:
        named = ", ".join(sorted(set(codes)))
        raise ProblemError(
            "validation_failed",
            detail=(
                f"{ALL_JURISDICTIONS!r} already names every registered jurisdiction, so it"
                f" cannot be combined with {named}: one of the two would be ignored and the"
                " response could not say which."
            ),
            errors=[
                {
                    "pointer": "/query/state",
                    "code": "state_set_mixed",
                    "detail": (
                        f"Ask for {ALL_JURISDICTIONS!r} or ask for codes, not both. A request"
                        " that narrows and widens in the same breath has no honest answer."
                    ),
                }
            ],
        )
    return None if every else tuple(sorted(set(codes)))


def _require_states(
    connection: Any, requested: tuple[str, ...] | None, registry: JurisdictionRegistry
) -> tuple[list[dict[str, Any]], tuple[str, ...]]:
    """The scope is required and refused when empty, because a facet cannot say so afterwards.

    A state with no rows would otherwise answer 200 with an empty list, which reads as "this
    operator list is empty" rather than "this state is not loaded" — and Montana and New
    Mexico make that distinction live rather than theoretical. `all` resolves against the
    registry, so a jurisdiction registered but not yet promoted widens the picker without
    emptying the answer.
    """
    found = rows(connection, _STATES)
    carrying = {row["state_code"] for row in found}
    registered = set(registry.by_prefix)
    if requested is None:
        resolved = tuple(sorted(registered & carrying))
        if resolved:
            return found, resolved
        _refuse_scope(found, registry, unregistered=(), unloaded=tuple(sorted(registered)))
    unregistered = tuple(sorted(set(requested or ()) - registered))
    unloaded = tuple(sorted(set(requested or ()) - carrying - set(unregistered)))
    if unregistered or unloaded:
        _refuse_scope(found, registry, unregistered=unregistered, unloaded=unloaded)
    return found, tuple(requested or ())


def _refuse_scope(
    found: list[dict[str, Any]],
    registry: JurisdictionRegistry,
    *,
    unregistered: tuple[str, ...],
    unloaded: tuple[str, ...],
) -> NoReturn:
    """One refusal for both ways a scope can name nothing, each saying which one it was."""
    if unregistered:
        offered = ", ".join(
            f"{code} ({_state_name(registry, code)})" for code in sorted(registry.by_prefix)
        )
        detail = (
            f"no jurisdiction is registered under state {', '.join(unregistered)}, so there is"
            f" nothing to count by. Registered states: {offered or 'none'}"
        )
        error = {
            "pointer": "/query/state",
            "code": "state_not_registered",
            "detail": (
                "A code the registry does not carry is not an empty facet list; it names no"
                " jurisdiction at all, and this operation says so rather than counting zero."
            ),
        }
    else:
        carried = ", ".join(
            f"{row['state_code']} — {_state_name(registry, row['state_code'])}"
            f" ({row['wells']:,} wells)"
            for row in found
        )
        detail = (
            f"the spine carries no well in state {', '.join(unloaded)}, so there is nothing to"
            f" count by. Loaded states: {carried or 'none'}"
        )
        error = {
            "pointer": "/query/state",
            "code": "state_not_loaded",
            "detail": (
                "A state whose ingest has not run is not an empty facet list; it is a"
                " different question, and this operation refuses rather than answer it as"
                " though the operators were counted and there were none."
            ),
        }
    raise ProblemError(
        "validation_failed",
        detail=detail,
        # The same list the success path serves, on the refusal, because a refusal that does
        # not say what you *can* ask for is a dead end: the panel's state picker is rebuilt
        # from this, and without it a link to a gated state renders a control with nothing in
        # it and no way back except editing the URL.
        extra={"states": _states(found, registry)},
        errors=[error],
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


def _states(
    loaded: list[dict[str, Any]], registry: JurisdictionRegistry
) -> list[dict[str, Any]]:
    """Every known state, with the ones holding no wells said rather than omitted.

    A picker built from the loaded set alone cannot distinguish "New Mexico has no operators"
    from "New Mexico is not promoted yet", and the second is the true one today.
    """
    carrying = {row["state_code"] for row in loaded}
    # The registry key here is the identity prefix, because `code` on this surface is the API
    # state code the collection filters by, not the jurisdiction code.
    codes = sorted(set(registry.by_prefix) | carrying)
    return [
        {"code": code, "name": _state_name(registry, code), "loaded": code in carrying}
        for code in codes
    ]


def _named(names: Any) -> str:
    """A list of names as a reader would say it, so a sentence reads at any set size."""
    listed = list(names)
    if len(listed) <= 1:
        return listed[0] if listed else "no jurisdiction"
    return f"{', '.join(listed[:-1])} and {listed[-1]}"


def _scope_name(registry: JurisdictionRegistry, codes: Sequence[str]) -> str:
    """What the scope is called, in the served names. One state reads exactly as it did."""
    return _named(_state_name(registry, code) for code in codes)


def _scope_phrase(registry: JurisdictionRegistry, codes: Sequence[str]) -> str:
    """The scope with the preposition that belongs to it, composed once and served.

    The panel says `across` for a set and `in` for one, and the caption is the largest sentence
    beside it. Two prepositions for one set 40 px apart is the drift `_caption`'s own comment
    already objects to about the sort control, so the server chooses the word: it is the one
    that knows how many jurisdictions are in the scope, and the client then composes nothing.
    """
    return f"{'across' if len(codes) > 1 else 'in'} {_scope_name(registry, codes)}"


def _selector(
    dimension: str,
    scope: str,
    q: str | None,
    part: str,
    value: str | None = None,
    jurisdiction: str | None = None,
) -> str:
    """One selector grammar for every figure: what was counted, of what, under which search.

    The scope goes through the identity helper because a comma list is outside the selector
    charset; a single code is plain, so a one-state handle is the byte it always was.
    """
    terms = [f"col={part}", f"dimension={dimension}", identity_selector_term("state", scope)]
    if jurisdiction is not None:
        terms.append(identity_selector_term("jurisdiction", jurisdiction))
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
    entries: Sequence[dict[str, Any]],
    *,
    scope: str,
    scope_phrase: str,
    dimension: str,
    q: str | None,
) -> dict[str, Any] | None:
    """The named bucket for wells the dimension has no value for, over the carried set.

    It is built outside the ranking and outside the search on purpose. A search over operator
    names cannot match a well that has no operator name, so filtering the absence bucket by `q`
    would make 70,039 Texas wells vanish the moment a reader typed a letter — the population
    would silently change under a control that says it only narrows a list.

    A jurisdiction whose absence a rule explains is not in it. Summed together, a registered
    absence and an unexplained one make a number that means two different things, and the
    bucket has one sentence to say what it is.
    """
    contributing = [
        entry
        for entry in entries
        if entry["dimension"] != ABSENT_BY_RULE and entry["absent"] > 0
    ]
    if not contributing:
        return None
    counted = _figure(
        {
            "wells": sum(entry["absent"] for entry in contributing),
            "derivation_id": max(
                (entry["derivation_id"] for entry in contributing if entry["derivation_id"]),
                default=None,
            ),
        },
        _selector(dimension, scope, q, "absent_wells"),
    )
    if counted is None:
        return None
    rules = sorted({entry["rule_id"] for entry in contributing if entry["rule_id"]})
    unregistered = [entry for entry in contributing if not entry["rule_id"]]
    rule = rules[0] if len(rules) == 1 and not unregistered else None
    noun = dimension.replace("_", " ")
    detail = (
        f"These wells carry no {noun}. The decision that this is an absence rather than an"
        " unknown is registered, with its evidence and its date."
        if rule
        else (
            f"These wells carry no {noun}. No conformance rule states what that absence means"
            " on this source, so this bucket counts them and claims nothing further about"
            " them (R8)."
            if not rules
            else (
                f"These wells carry no {noun}, in"
                f" {_named(entry['name'] for entry in contributing)}. Not every one of them"
                " has a registered decision about what that absence means, so the bucket"
                " cites none of them here; `jurisdictions` says which rule covers which (R8)."
            )
        )
    )
    excluded = [entry for entry in entries if entry["dimension"] == ABSENT_BY_RULE]
    if excluded:
        detail += (
            f" {_named(entry['name'] for entry in excluded)} carries no {noun} at all and is"
            " counted separately, under the rule that says so, rather than folded in here."
        )
    # The search moves every other figure in the response and leaves this one whole-scope, so
    # the sentence names the population the count belongs to rather than leaving the reader to
    # infer it from a total that is no longer on the surface.
    if q is not None:
        detail += (
            f" The search for {q!r} did not narrow this bucket: a well with no {noun} matches"
            f" no {noun} text, so this is every such well"
            f" {scope_phrase}, not a share of the matches."
        )
    return {
        "label": ABSENCE_LABEL,
        "detail": detail,
        "rule_id": rule,
        "wells": counted,
        "links": {"rule": f"/v1/conformance/{rule}"} if rule else {},
    }


def _remainder(
    row: dict[str, Any] | None, *, scope: str, dimension: str, q: str | None, top: int
) -> dict[str, Any] | None:
    if row is None or row["values"] in (None, 0):
        return None
    counted = _figure(row, _selector(dimension, scope, q, "remainder_wells"))
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
    *,
    dimension: str,
    scope_phrase: str,
    shown: int,
    distinct: int,
    q: str | None,
    sort: str,
    order: str,
) -> str:
    """The one sentence that has to be true: what is on screen, and what it is a cut of.

    `order` is as load-bearing as `sort`: `count:asc` serves the values with the *fewest* wells,
    and a sentence naming the most describes a list the reader is not looking at.
    """
    noun = dimension.replace("_", " ")
    name = scope_phrase
    if distinct == 0:
        return (
            f"No {noun} {name} matches {q!r}. The search ran over all of them, so this is"
            " the whole answer."
            if q is not None
            else f"No well {name} carries a {noun}."
        )
    matching = f" matching {q!r}" if q is not None else ""
    of = f"{distinct:,} {noun} value{'s' if distinct != 1 else ''}{matching} {name}"
    descending = order == "desc"
    # The words the direction button beside this sentence uses (`wells-by.ts` directionLabel):
    # one vocabulary, or two controls describe the same parameter differently 40 px apart.
    by_value = f"value, {'Z to A' if descending else 'A to Z'}"
    if shown >= distinct:
        ranking = (
            f"well count, {'highest' if descending else 'lowest'} first"
            if sort == "count"
            else by_value
        )
        return f"All {of}, ranked by {ranking}."
    if sort == "count":
        extreme = "most" if descending else "fewest"
        plural = "s" if shown != 1 else ""
        return f"The {shown:,} {noun} value{plural} with the {extreme} wells, of {of}."
    return f"{shown:,} of {of}, ranked by {by_value}."


def _bucket_link(dimension: str, value: str, scope: str) -> dict[str, str]:
    """A bucket the collection cannot reproduce gets no link rather than a link that lies.

    The scope rides as the request echo rather than as the resolved codes: `/v1/wells` reads
    the same grammar, so `state=all` there is this response's own set and the link cannot
    narrow to a population the count was not taken over.
    """
    name = DIMENSIONS[dimension]["filter"]
    if not name:
        return {}
    # Encoded, not interpolated: `DIAMONDBACK E&P LLC` ends at the ampersand written verbatim.
    return {"wells": f"/v1/wells?{urlencode([(name, value), ('state', scope)])}"}


def _jurisdictions(
    found: Sequence[dict[str, Any]],
    *,
    codes: Sequence[str],
    dimension: str,
    scope: str,
    registry: JurisdictionRegistry,
) -> list[dict[str, Any]]:
    """The set the counts were taken over, and what each jurisdiction does with the dimension.

    R8 decides the middle case and the data decides the first: a jurisdiction that holds no
    value is `absent_by_rule` only where a registered rule says what that means, and
    `absent_unregistered` otherwise, which is a disclosure rather than a claim.
    """
    counted = {row["value"]: row for row in found if row["kind"] == "jurisdiction"}
    entries: list[dict[str, Any]] = []
    for code in codes:
        row = counted.get(code)
        rule = _absence_rule(registry, code, dimension)
        values = int(row["values"]) if row and row["values"] else 0
        contributes = bool(row and row["wells"])
        if not contributes:
            carries = NO_WELLS_IN_SCOPE
        else:
            carries = CARRIED if values else ABSENT_BY_RULE if rule else ABSENT_UNREGISTERED
        entries.append(
            {
                "code": code,
                "name": _state_name(registry, code),
                "wells": _figure(
                    row,
                    _selector(dimension, scope, None, "jurisdiction_wells", jurisdiction=code),
                ),
                "dimension": carries,
                "rule_id": rule,
                # Not served: the split of the absence bucket the two arms above are built
                # from. `wells` is the whole contribution, and for an absent_by_rule
                # jurisdiction every one of them is absent, which is what makes the served
                # figures reconcile without a second count beside each one.
                "absent": int(row["absent"]) if row and row["absent"] else 0,
                "derivation_id": row["derivation_id"] if row else None,
            }
        )
    return entries


def _warnings(
    *,
    absence: dict[str, Any] | None,
    truncated: bool,
    q: str | None,
    jurisdictions: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    by_rule = [entry for entry in jurisdictions if entry["dimension"] == ABSENT_BY_RULE]
    if by_rule:
        named = _named(entry["name"] for entry in by_rule)
        # The identity named here is the unsearched one. Under a `q` the ranked arms read the
        # matched population and reconcile against `matched_wells`, which is what the operation
        # description says two paragraphs earlier -- so naming `wells` under a search sends the
        # reader to check an arithmetic that does not hold on the response in front of them.
        reconciles = (
            "so buckets and remainder sum to `matched_wells`, and neither they nor the"
            " absence bucket account for these"
            if q is not None
            else "so buckets, remainder and absence sum to the total only once they are"
            " added back"
        )
        warnings.append(
            {
                "code": "dimension_absent_by_rule",
                "detail": (
                    f"{named} carries no value of this dimension at all, under a registered"
                    " rule. Those wells are counted in `jurisdictions` and are outside the"
                    f" `not reported` bucket, {reconciles}."
                ),
                "pointer": "/jurisdictions",
            }
        )
    if absence is not None and absence["rule_id"] is None:
        warnings.append(
            {
                "code": "absence_unregistered",
                # What `absence.detail` does not already say. The panel renders this inside the
                # block the pointer names, and two paragraphs of one fact is one too many.
                "detail": (
                    "This bucket is a count, not a finding: it is not citable as one until the"
                    " absence is registered as a conformance row (R8)."
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
        "How many current wells carry each value of one dimension, ranked, over one"
        " jurisdiction or several. This"
        " is the question a screening pass opens with — who operates here, what is in this"
        " county, how old is the completion population — asked of the spine rather than of a"
        " page of it. The population is every current well the state has promoted, so the"
        " ranking does not move with the viewport, with paging, or with which rows a grid has"
        " fetched."
        " Scope is a set of states and is required: repeat `state`, comma-separate the codes,"
        " or send `all` for every registered jurisdiction the spine carries wells for."
        " `jurisdictions` names the set the counts were taken over and says, per jurisdiction,"
        " whether it carries this dimension. Operator names arrive per source and"
        " `lineage.operator_aliases` carries no row for any state served here, so the same"
        " company spelled two ways in two jurisdictions is two values; summing them across a"
        " border would be an aliasing decision no conformance rule has made, and this operation"
        " declines to make it silently (R8) — a combined bucket is one spelling in one column,"
        " never two spellings added together."
        " Three things about what the list is not are counted rather than implied: `remainder`"
        " holds every value below the cut and the wells they carry, `distinct_values` is how"
        " many values the state holds in total, and `absence` is its own named bucket for wells"
        " the dimension has no value for. The absence bucket never enters the ranking — on the"
        " current Texas load it would outrank all 9,369 operators — and never enters the"
        " search, because a well with no name matches no name. It counts only jurisdictions"
        " that carry the dimension: one holding no value at all under a registered rule is"
        " named in `jurisdictions` instead, because a registered absence and an unexplained"
        " one summed together make a number with two meanings. With no search in force,"
        " `buckets` + `remainder` + `absence` + the `absent_by_rule` jurisdictions\' `wells`"
        " sum to `wells`. Under a `q` the ranked arms are searched and `absence` is not, so"
        " `buckets` + `remainder` sum to `matched_wells` instead and that is what the served"
        " figures reconcile against."
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
                    "The API state codes, the first two digits of every API-10 in the bucket."
                    " Repeat it, comma-separate the codes, or send `all` for every registered"
                    " jurisdiction — `all` is read from the registry at request time, so a"
                    " newly registered state joins the answer without a client change."
                    " Required, and refused when the spine holds no well for a code or the"
                    " registry knows none: a state whose ingest has not run is a different"
                    " answer from a state with no operators, and only one of them is worth"
                    " serving as an empty list."
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
        list[StateTerm],
        Query(
            description=(
                "API state codes, e.g. 33 for North Dakota. Repeat the parameter"
                " (`?state=33&state=42`), comma-separate the codes (`?state=33,42`), or send"
                " `all` for every registered jurisdiction. Required."
            ),
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
    consume_rate_limit(
        connection, principal, operation="get_well_facets", limit=FACET_REQUESTS_PER_MINUTE
    )
    registry = jurisdictions(connection)
    requested = state_set(state)
    loaded, codes = _require_states(connection, requested, registry)
    # The request echo, and the one string every selector, caption and bucket link carries.
    # `all` stays `all` rather than being enumerated: the collection reads the same grammar and
    # resolves it against the same registry, so the link is exact today. It is a live term, not
    # a snapshot -- a jurisdiction registering after the count widens what the link returns, and
    # `jurisdictions` beside the number is what names the set it was actually taken over. A
    # traversal of that link does not widen under way; /v1/wells fingerprints its cursor over
    # the resolved codes.
    scope = ALL_JURISDICTIONS if requested is None else ",".join(codes)
    scope_name = _scope_name(registry, codes)
    scope_phrase = _scope_phrase(registry, codes)
    scoped = (_SCOPED_AS_OF if as_of is not None else _SCOPED_LATEST).format(
        column=DIMENSIONS[by]["column"], join=DIMENSIONS[by].get("join", "")
    )
    statement = _FACETS.format(scoped=scoped, order=_VALUE_SORTS[(sort, order)])
    found = rows(
        connection, statement, {"states": list(codes), "as_of": as_of, "q": q, "top": top}
    )
    by_kind: dict[str, list[dict[str, Any]]] = {}
    for row in found:
        by_kind.setdefault(row["kind"], []).append(row)
    listed_kinds = ("bucket", "jurisdiction")
    one = {kind: group[0] for kind, group in by_kind.items() if kind not in listed_kinds}
    listed = sorted(by_kind.get("bucket", []), key=lambda row: row["rank"])

    entries = _jurisdictions(
        found, codes=codes, dimension=by, scope=scope, registry=registry
    )
    absence = _absence(entries, scope=scope, scope_phrase=scope_phrase, dimension=by, q=q)
    remainder = _remainder(one.get("remainder"), scope=scope, dimension=by, q=q, top=top)
    scope_row = one.get("scope")
    data: dict[str, Any] = {
        "state": scope,
        "state_name": scope_name,
        "dimension": by,
        "dimension_title": DIMENSIONS[by]["title"],
        "sort": sort,
        "order": order,
        "q": q,
        "top": top,
        "distinct_values": int(scope_row["values"]) if scope_row and scope_row["values"] else 0,
        "caption": _caption(
            dimension=by,
            scope_phrase=scope_phrase,
            shown=len(listed),
            distinct=(
                int(one["matched"]["values"])
                if q is not None and one.get("matched") and one["matched"]["values"]
                else (int(scope_row["values"]) if scope_row and scope_row["values"] else 0)
            ),
            q=q,
            sort=sort,
            order=order,
        ),
        "buckets": [
            {
                "value": row["value"],
                "wells": _figure(row, _selector(by, scope, q, "wells", row["value"])),
                "links": _bucket_link(by, row["value"], scope),
            }
            for row in listed
        ],
        "remainder": remainder,
        "absence": absence,
        "wells": _figure(scope_row, _selector(by, scope, None, "scope_wells")),
        "matched_wells": (
            _figure(one.get("matched"), _selector(by, scope, q, "matched_wells"))
            if q is not None
            else None
        ),
        "jurisdictions": [
            {key: entry[key] for key in ("code", "name", "wells", "dimension", "rule_id")}
            for entry in entries
        ],
        "states": _states(loaded, registry),
        "rules": sorted(
            ({absence["rule_id"]} if absence and absence["rule_id"] else set())
            | {entry["rule_id"] for entry in entries if entry["rule_id"]}
        ),
    }
    data = register_response_figures(
        connection,
        data,
        dataset="api.well_facets",
        operation_id="get_well_facets",
        locator=request.url.path,
        partition=dict(
            [
                _partition_term("state", scope),
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
            absence=absence,
            truncated=remainder is not None,
            q=q,
            jurisdictions=entries,
        ),
        links={rule: f"/v1/conformance/{rule}" for rule in data["rules"]},
        explain=inline_for(connection, explain),
    )
