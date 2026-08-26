"""Knowledge-time read paths; downstream packages never query canonical directly."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import psycopg
from psycopg.rows import dict_row

from glasswell.lineage.models import InputRef


class AsOfViolation(RuntimeError):
    """A source cannot prove it existed at the requested knowledge vintage."""


@dataclass(frozen=True, slots=True)
class FeatureSourceSnapshot:
    rows: tuple[Mapping[str, object], ...]
    inputs: tuple[InputRef, ...]


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
           array_agg(distinct a.formation_group order by a.formation_group)
               filter (where a.formation_group is not null) as formations
      from completion_versions c
      left join alias_versions a
        on a.formation_raw = c.pool_reported
       and a.vintage_rank = 1
     where c.vintage_rank = 1
     group by c.api10
)
"""

_FEATURE_ROWS = (
    _FEATURE_CTES
    + """
select s.api10, s.spud_date, s.completion_date, f.formations
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
  from completion_versions
 where vintage_rank = 1
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
) -> FeatureSourceSnapshot:
    """Resolve the feature source rows and their lineage at one knowledge vintage."""
    query_params = {
        "as_of": as_of,
        "state_code": state_code,
        "basin": basin,
        "min_confidence": min_confidence,
        "formation_source_id": formation_source_id,
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
        inputs=_input_refs(source_inputs, alias_vintage=alias_vintage),
    )


def _input_refs(
    rows: Sequence[Mapping[str, object]], *, alias_vintage: date | None
) -> tuple[InputRef, ...]:
    vintages: dict[str, date] = {}
    for row in rows:
        identifier = str(row["derivation_id"])
        vintage = row["source_vintage"]
        if not isinstance(vintage, date):
            raise AsOfViolation(f"canonical input {identifier} has no knowledge vintage")
        vintages[identifier] = max(vintage, vintages.get(identifier, vintage))
    refs = [
        InputRef(kind="derivation", ref_id=identifier, as_of_vintage=vintage)
        for identifier, vintage in sorted(vintages.items())
    ]
    refs.append(
        InputRef(
            kind="external",
            ref_id="lineage.formation_aliases",
            as_of_vintage=alias_vintage,
            role="crosswalk",
        )
    )
    return tuple(ref.model_copy(update={"ord": ordinal}) for ordinal, ref in enumerate(refs))
