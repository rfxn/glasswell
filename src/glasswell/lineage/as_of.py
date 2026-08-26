"""Knowledge-time read paths; downstream packages never query canonical directly."""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal

import psycopg
from psycopg.rows import dict_row

from glasswell.lineage.models import InputRef
from glasswell.lineage.serialization import hash_payload


class AsOfViolation(RuntimeError):
    """A source cannot prove it existed at the requested knowledge vintage."""


@dataclass(frozen=True, slots=True)
class FeatureSourceSnapshot:
    rows: tuple[Mapping[str, object], ...]
    inputs: tuple[InputRef, ...]


@dataclass(frozen=True, slots=True)
class ModelContextSnapshot:
    rows: tuple[Mapping[str, object], ...]
    inputs: tuple[InputRef, ...]


FormationObservationPolicy = Literal["all_observed", "initial_observed"]


_FEATURE_CTES = """
with well_versions as (
    select w.api10, w.spud_date, w.completion_date, w.derivation_id,
           greatest(w.effective_from, m.fetch_vintage,
                    coalesce(d.created_vintage, m.fetch_vintage)) as source_vintage,
           row_number() over (
               partition by w.api10
               order by w.effective_from desc, w.derivation_id desc) as vintage_rank
      from canonical.wells w
      join lineage.manifests m on m.manifest_id = w.source_manifest_id
      join lineage.derivations d on d.derivation_id = w.derivation_id
     where w.state_code = %(state_code)s
       and w.basin = %(basin)s
       and w.effective_from <= %(as_of)s
       and m.fetch_vintage <= %(as_of)s
       and (d.created_vintage is null or d.created_vintage <= %(as_of)s)
),
subjects as (
    select api10, spud_date, completion_date, derivation_id, source_vintage
      from well_versions
     where vintage_rank = 1
       and completion_date is not null
       and completion_date <= %(as_of)s
),
completion_versions as (
    select c.api10, c.completion_key, c.source_id, c.production_month, c.pool_reported,
           c.derivation_id,
           greatest(c.report_vintage, m.fetch_vintage,
                    coalesce(d.created_vintage, m.fetch_vintage)) as source_vintage,
           row_number() over (
               partition by c.completion_key, c.source_id, c.production_month
               order by c.report_vintage desc, c.derivation_id desc) as vintage_rank
      from canonical.well_completions c
      join subjects s on s.api10 = c.api10
      join lineage.manifests m on m.manifest_id = c.source_manifest_id
      join lineage.derivations d on d.derivation_id = c.derivation_id
     where c.report_vintage <= %(as_of)s
       and m.fetch_vintage <= %(as_of)s
       and (d.created_vintage is null or d.created_vintage <= %(as_of)s)
),
current_completions as (
    select api10, completion_key, source_id, production_month, pool_reported,
           derivation_id, source_vintage
      from completion_versions
     where vintage_rank = 1
),
eligible_completions as (
    select *
      from current_completions
     where %(formation_observation_policy)s = 'all_observed'
        or (source_id = %(formation_source_id)s and pool_reported is not null)
),
first_completion_months as (
    select api10, min(production_month) as production_month
      from eligible_completions
     group by api10
),
selected_completions as (
    select c.*
      from eligible_completions c
      join first_completion_months f using (api10)
     where %(formation_observation_policy)s = 'all_observed'
        or c.production_month = f.production_month
),
alias_versions as (
    select formation_raw, coalesce(formation_group, formation) as formation_group,
           effective_from, created_vintage,
           row_number() over (
               partition by formation_raw
               order by effective_from desc, coalesce(formation_group, formation)) as vintage_rank
      from lineage.formation_aliases
     where effective_from <= %(as_of)s
       and created_vintage <= %(as_of)s
       and confidence >= %(min_confidence)s
       and source_id = %(formation_source_id)s
),
formation_groups as (
    select c.api10,
           min(c.production_month) as formation_first_month,
           (min(c.production_month)
               + make_interval(days => %(source_publication_lag_days)s))::date
               as formation_available_on,
           array_agg(distinct c.pool_reported order by c.pool_reported)
               filter (where c.pool_reported is not null) as formation_pools,
           array_agg(distinct a.formation_group order by a.formation_group)
               filter (where a.formation_group is not null) as formations
      from selected_completions c
      left join alias_versions a
        on a.formation_raw = c.pool_reported
       and a.vintage_rank = 1
     group by c.api10
)
"""

_FEATURE_ROWS = (
    _FEATURE_CTES
    + """
select s.api10, s.spud_date, s.completion_date, f.formation_first_month,
       f.formation_available_on, f.formation_pools, f.formations
  from subjects s
  left join formation_groups f on f.api10 = s.api10
 order by s.api10
"""
)

_FEATURE_INPUTS = (
    _FEATURE_CTES
    + """
select derivation_id, source_vintage
  from subjects
union
select derivation_id, source_vintage
  from selected_completions
order by derivation_id, source_vintage
"""
)


def read_feature_snapshot(
    connection: psycopg.Connection,
    *,
    as_of: date,
    state_code: str,
    basin: str,
    min_confidence: Decimal,
    formation_source_id: str,
    formation_observation_policy: FormationObservationPolicy = "all_observed",
    source_publication_lag_days: int = 0,
) -> FeatureSourceSnapshot:
    """Resolve the feature source rows and their lineage at one knowledge vintage."""
    if formation_observation_policy not in ("all_observed", "initial_observed"):
        raise ValueError(
            f"unsupported formation observation policy {formation_observation_policy!r}"
        )
    if source_publication_lag_days < 0:
        raise ValueError("source publication lag must be nonnegative")
    query_params = {
        "as_of": as_of,
        "state_code": state_code,
        "basin": basin,
        "min_confidence": min_confidence,
        "formation_source_id": formation_source_id,
        "formation_observation_policy": formation_observation_policy,
        "source_publication_lag_days": source_publication_lag_days,
    }
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            "select count(*) as unvintaged from lineage.formation_aliases"
            " where source_id = %s and effective_from <= %s and confidence >= %s"
            " and created_vintage is null",
            (formation_source_id, as_of, min_confidence),
        )
        unvintaged = cursor.fetchone()["unvintaged"]
        if unvintaged:
            raise AsOfViolation(
                f"{unvintaged} {formation_source_id} formation aliases lack created_vintage"
            )
        cursor.execute(_FEATURE_ROWS, query_params)
        rows = tuple(cursor.fetchall())
        alias_selector = _formation_alias_selector(
            cursor,
            rows=rows,
            as_of=as_of,
            min_confidence=min_confidence,
            formation_source_id=formation_source_id,
            formation_observation_policy=formation_observation_policy,
        )
        cursor.execute(_FEATURE_INPUTS, query_params)
        source_inputs = cursor.fetchall()
        cursor.execute(
            "select max(created_vintage) from lineage.formation_aliases"
            " where effective_from <= %s and created_vintage <= %s"
            " and confidence >= %s and source_id = %s",
            (as_of, as_of, min_confidence, formation_source_id),
        )
        alias_vintage = cursor.fetchone()["max"]
    return FeatureSourceSnapshot(
        rows=rows,
        inputs=_input_refs(
            source_inputs,
            alias_vintage=alias_vintage,
            alias_selector=alias_selector,
        ),
    )


def _formation_alias_selector(
    cursor: psycopg.Cursor,
    *,
    rows: Sequence[Mapping[str, object]],
    as_of: date,
    min_confidence: Decimal,
    formation_source_id: str,
    formation_observation_policy: FormationObservationPolicy,
) -> str | None:
    if formation_observation_policy == "all_observed":
        return None
    pools = sorted(
        {
            str(pool)
            for row in rows
            for pool in (row["formation_pools"] or ())
        }
    )
    cursor.execute(
        "select distinct on (formation_raw) formation_raw,"
        " coalesce(formation_group, formation) as formation_group,"
        " confidence::text as confidence, effective_from, created_vintage, source_id"
        " from lineage.formation_aliases"
        " where effective_from <= %s and created_vintage <= %s and confidence >= %s"
        " and source_id = %s and formation_raw = any(%s)"
        " order by formation_raw, effective_from desc,"
        " coalesce(formation_group, formation)",
        (as_of, as_of, min_confidence, formation_source_id, pools),
    )
    return "sha256:" + hash_payload(
        {"reported_pools": pools, "aliases": cursor.fetchall()}
    )


def _input_refs(
    rows: Sequence[Mapping[str, object]],
    *,
    alias_vintage: date | None,
    alias_selector: str | None,
) -> tuple[InputRef, ...]:
    refs = list(_derivation_input_refs(rows))
    refs.append(
        InputRef(
            kind="external",
            ref_id="lineage.formation_aliases",
            selector=alias_selector,
            as_of_vintage=alias_vintage,
            role="crosswalk",
        )
    )
    return tuple(ref.model_copy(update={"ord": ordinal}) for ordinal, ref in enumerate(refs))


def _derivation_input_refs(
    rows: Sequence[Mapping[str, object]],
) -> tuple[InputRef, ...]:
    vintages: dict[str, date] = {}
    for row in rows:
        identifier = str(row["derivation_id"])
        vintage = row["source_vintage"]
        if not isinstance(vintage, date):
            raise AsOfViolation(f"canonical input {identifier} has no knowledge vintage")
        vintages[identifier] = max(vintage, vintages.get(identifier, vintage))
    refs = tuple(
        InputRef(kind="derivation", ref_id=identifier, as_of_vintage=vintage)
        for identifier, vintage in sorted(vintages.items())
    )
    return tuple(ref.model_copy(update={"ord": ordinal}) for ordinal, ref in enumerate(refs))


_MODEL_CONTEXT_CTES = """
with well_versions as (
    select w.api10, w.county_code_at_permit, w.basin, w.completion_date,
           w.confidential_flag, w.derivation_id,
           greatest(w.effective_from, m.fetch_vintage,
                    coalesce(d.created_vintage, m.fetch_vintage)) as source_vintage,
           row_number() over (
               partition by w.api10
               order by w.effective_from desc, w.derivation_id desc) as vintage_rank
      from canonical.wells w
      join lineage.manifests m on m.manifest_id = w.source_manifest_id
      join lineage.derivations d on d.derivation_id = w.derivation_id
     where w.api10 = any(%(api10s)s)
       and w.basin = %(basin)s
       and w.effective_from <= %(as_of)s
       and m.fetch_vintage <= %(as_of)s
       and (d.created_vintage is null or d.created_vintage <= %(as_of)s)
),
subjects as (
    select * from well_versions where vintage_rank = 1
),
spatial_rows as (
    select s.api10, s.geom_type, s.geom_key, s.geom, s.derivation_id,
           greatest(m.fetch_vintage, coalesce(d.created_vintage, m.fetch_vintage))
               as source_vintage
      from canonical.well_spatial s
      join lineage.manifests m on m.manifest_id = s.source_manifest_id
      join lineage.derivations d on d.derivation_id = s.derivation_id
     where s.api10 = any(%(api10s)s)
       and s.geom_type in ('surface', 'lateral')
       and m.fetch_vintage <= %(as_of)s
       and (d.created_vintage is null or d.created_vintage <= %(as_of)s)
),
surfaces as (
    select api10, count(*) as surface_count,
           case when count(*) = 1 then min(ST_X(ST_Transform(geom, 5070))) end as surface_x_m,
           case when count(*) = 1 then min(ST_Y(ST_Transform(geom, 5070))) end as surface_y_m
      from spatial_rows where geom_type = 'surface' group by api10
),
laterals as (
    select api10, sum(ST_Length(geom::geography) / 0.3048) as lateral_length_ft
      from spatial_rows where geom_type = 'lateral' group by api10
)
"""

_MODEL_CONTEXT_ROWS = (
    _MODEL_CONTEXT_CTES
    + """
select s.api10, s.county_code_at_permit as area, s.basin, s.completion_date,
       s.confidential_flag, coalesce(p.surface_count, 0) as surface_count,
       p.surface_x_m, p.surface_y_m, l.lateral_length_ft
  from subjects s
  left join surfaces p using (api10)
  left join laterals l using (api10)
 order by s.api10
"""
)

_MODEL_CONTEXT_INPUTS = (
    _MODEL_CONTEXT_CTES
    + """
select derivation_id, source_vintage from subjects
union
select derivation_id, source_vintage from spatial_rows
order by derivation_id, source_vintage
"""
)

_MODEL_PRODUCTION_CTES = """
with production_versions as (
    select p.api10, p.production_month, p.stream, p.volume, p.unit, p.days_produced,
           p.null_semantics, p.derivation_id,
           greatest(p.report_vintage, m.fetch_vintage,
                    coalesce(d.created_vintage, m.fetch_vintage)) as source_vintage,
           row_number() over (
               partition by p.entity_type, p.entity_key, p.production_month, p.stream,
                            p.source_id
               order by p.report_vintage desc) as vintage_rank
      from canonical.production_monthly p
      join lineage.manifests m on m.manifest_id = p.source_manifest_id
      join lineage.derivations d on d.derivation_id = p.derivation_id
     where p.api10 = any(%(api10s)s)
       and p.entity_type = 'well'
       and p.source_id = %(source_id)s
       and p.report_vintage <= %(as_of)s
       and m.fetch_vintage <= %(as_of)s
       and (d.created_vintage is null or d.created_vintage <= %(as_of)s)
),
selected as (
    select * from production_versions where vintage_rank = 1
)
"""

_MODEL_PRODUCTION_ROWS = (
    _MODEL_PRODUCTION_CTES
    + """
select api10, production_month,
       max(volume) filter (where stream = 'oil') as oil_volume,
       max(unit) filter (where stream = 'oil') as oil_unit,
       max(days_produced) filter (where stream = 'oil') as oil_days_produced,
       max(null_semantics) filter (where stream = 'oil') as oil_null_semantics,
       max(volume) filter (where stream = 'gas') as gas_volume,
       max(unit) filter (where stream = 'gas') as gas_unit,
       max(days_produced) filter (where stream = 'gas') as gas_days_produced,
       max(null_semantics) filter (where stream = 'gas') as gas_null_semantics,
       max(volume) filter (where stream = 'water') as water_volume,
       max(unit) filter (where stream = 'water') as water_unit,
       max(days_produced) filter (where stream = 'water') as water_days_produced,
       max(null_semantics) filter (where stream = 'water') as water_null_semantics,
       max(source_vintage) as source_vintage,
       count(*) filter (where stream = 'oil') as oil_rows,
       count(*) filter (where stream = 'gas') as gas_rows,
       count(*) filter (where stream = 'water') as water_rows
  from selected
 group by api10, production_month
 order by api10, production_month
"""
)

_MODEL_PRODUCTION_INPUTS = (
    _MODEL_PRODUCTION_CTES
    + """
select distinct derivation_id, source_vintage from selected
order by derivation_id, source_vintage
"""
)


def read_model_context_snapshot(
    connection: psycopg.Connection,
    *,
    api10s: Sequence[str],
    basin: str,
    as_of: date,
) -> ModelContextSnapshot:
    """Read well and spatial control context without crossing the knowledge cut."""
    if not api10s:
        return ModelContextSnapshot(rows=(), inputs=())
    params = {"api10s": list(api10s), "basin": basin, "as_of": as_of}
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(_MODEL_CONTEXT_ROWS, params)
        rows = tuple(cursor.fetchall())
        cursor.execute(_MODEL_CONTEXT_INPUTS, params)
        inputs = _derivation_input_refs(cursor.fetchall())
    return ModelContextSnapshot(rows=rows, inputs=inputs)


@contextmanager
def read_model_production_snapshot(
    connection: psycopg.Connection,
    *,
    api10s: Sequence[str],
    source_id: str,
    as_of: date,
) -> Iterator[tuple[Iterator[Mapping[str, object]], tuple[InputRef, ...]]]:
    """Stream canonical well-months and return the exact derivations selected by the read."""
    params = {"api10s": list(api10s), "source_id": source_id, "as_of": as_of}
    with connection.cursor(row_factory=dict_row) as input_cursor:
        input_cursor.execute(_MODEL_PRODUCTION_INPUTS, params)
        inputs = _derivation_input_refs(input_cursor.fetchall())
    cursor_name = "glasswell_model_production"
    with connection.cursor(name=cursor_name, row_factory=dict_row) as cursor:
        cursor.itersize = 10_000
        cursor.execute(_MODEL_PRODUCTION_ROWS, params)
        yield iter(cursor), inputs
