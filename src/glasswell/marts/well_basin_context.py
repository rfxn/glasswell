"""Refresh marts.well_basin_context: which published basin a well's geometry falls in.

Marts read canonical only (blueprint §3.0.1). This one reads canonical.wells_latest,
canonical.well_spatial and canonical.basin_boundaries, and touches no staging table.

Driven off `wells_latest` and left-joined to geometry, never the other way round: well_spatial
holds surface points for 1,486 api10s that have no row in wells_latest, 1,400 of them Montana,
and a mart driven off geometry would serve those as rows with no well behind them. Driven off
the well list the row count is the well count by construction, and a well with no geometry gets
`no_geometry` rather than being absent -- which is a different fact from being outside every
boundary, and both are different from not being asked.

Rebuilt, never appended: one row per well, replaced whole.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import dataclass

import psycopg
from psycopg.rows import dict_row

from glasswell.db.dsn import add_dsn_argument, resolve_dsn
from glasswell.ingest.base import resolve_environment
from glasswell.lineage.capture import derive, lineage_session
from glasswell.lineage.jurisdictions import load_jurisdictions
from glasswell.lineage.models import InputRef, OutputSpec
from glasswell.lineage.serialization import hash_payload
from glasswell.lineage.store import PostgresRecorder
from glasswell.seed.conformance_basin_context import BASIN_CONTEXT, GEOMETRY_BASIS, OUTSIDE

MART = "marts.well_basin_context"

IN_BOUNDARY = "in_published_boundary"
NO_GEOMETRY = "no_geometry"
PLAYS = "plays"
NO_PLAY = "no_play_at_this_location"
AGREES = "agrees"
DISAGREES = "disagrees"
NOT_LABELLED = "not_labelled"
NO_LABEL = "no_label_to_compare"

# One containing basin, chosen by published area ascending so the answer is the most specific
# boundary that contains the point and is the same on every run. Overlap is served rather than
# arbitrated away: `basin_overlap` carries how many contained it, so a reader can see when the
# publisher's own polygons disagree with each other. Measured on the spine 2026-09-03: 7 wells
# of the 581,684 with a surface point fall in two published basins, and none in three.
_BASIN = """
    left join lateral (
        select b.boundary_id, b.name, b.vintage_label,
               count(*) over () as overlap
          from canonical.basin_boundaries b
         where b.boundary_kind = 'basin'
           and s.geom is not null
           and st_intersects(b.geom, s.geom)
         order by b.area_sq_mi asc nulls last, b.boundary_id
         limit 1) basin on true
"""

# What the well was asked against, for the rows no polygon contained. "Outside" is an answer
# about a boundary set, and a reader who reads it is owed the set's own published vintage --
# which is the same for every well the set was asked about, so it is read once per run.
_SET_VINTAGE = """
select string_agg(distinct vintage_label, ' · ' order by vintage_label)
  from canonical.basin_boundaries
 where boundary_kind = 'basin'
"""

# Every play the point falls in, because plays stack and picking one would be a claim nobody
# published. Empty array, never null: the class beside it says which of the two absences it is.
_PLAYS = """
    left join lateral (
        select coalesce(array_agg(p.name order by p.name), '{}'::text[]) as names
          from canonical.basin_boundaries p
         where p.boundary_kind = 'play'
           and s.geom is not null
           and st_intersects(p.geom, s.geom)) plays on true
"""

# The surface point, and only that, in this release. A Texas well has a surface point and a
# bottom hole and a long lateral can cross a boundary, so which end answered is registered as
# the rule's decision and served on the row.
_SURFACE = """
    left join lateral (
        select w.geom
          from canonical.well_spatial w
         where w.api10 = l.api10 and w.geom_type = %(geometry_basis)s
         order by w.geom_key
         limit 1) s on true
"""

CONTEXT_QUERY = f"""
select l.api10,
       l.state_code,
       l.basin as basin_label_filed,
       basin.boundary_id,
       basin.name as basin_name,
       basin.vintage_label as boundary_vintage,
       coalesce(basin.overlap, 0) as basin_overlap,
       coalesce(plays.names, '{{}}'::text[]) as play_name,
       s.geom is not null as has_geometry
  from canonical.wells_latest l
{_SURFACE}
{_BASIN}
{_PLAYS}
 order by l.api10
"""

# The wells this mart is a statement about, as derivation refs: without them the refresh is a
# graph node with no edge leaving it, and a served basin resolves to a run that cannot be
# walked back to the regulator file. The boundary rows carry their own derivations and are
# named beside them, because the answer is a join of the two.
_INPUT_DERIVATIONS = """
select derivation_id, created_vintage
  from lineage.derivations
 where derivation_id in (select derivation_id from canonical.wells)
    or derivation_id in (select derivation_id from canonical.well_spatial)
    or derivation_id in (select derivation_id from canonical.basin_boundaries)
 order by derivation_id
"""

_INSERT = f"""
insert into {MART}
    (api10, state_code, basin_name, basin_class, basin_overlap, play_name, play_class,
     basin_label_filed, label_class, label_agrees, boundary_vintage, geometry_basis,
     boundary_id, rule_id, derivation_id)
values (%(api10)s, %(state_code)s, %(basin_name)s, %(basin_class)s, %(basin_overlap)s,
        %(play_name)s, %(play_class)s, %(basin_label_filed)s, %(label_class)s,
        %(label_agrees)s, %(boundary_vintage)s, %(geometry_basis)s, %(boundary_id)s,
        %(rule_id)s, %(derivation_id)s)
"""


@dataclass(frozen=True, slots=True)
class BasinContextRefresh:
    derivation_id: str
    rows: int
    inside: int
    outside: int
    no_geometry: int
    disagreeing: int

    def as_dict(self) -> dict[str, object]:
        return {
            "derivation_id": self.derivation_id,
            "rows": self.rows,
            "inside": self.inside,
            "outside": self.outside,
            "no_geometry": self.no_geometry,
            "disagreeing": self.disagreeing,
        }


def classify(
    row: dict[str, object], rule_id: str | None, set_vintage: str | None = None
) -> dict[str, object]:
    """One canonical row to one mart row. Every absence carries a class, never a silence."""
    has_geometry = bool(row["has_geometry"])
    basin_name = row["basin_name"]
    if not has_geometry:
        basin_class = NO_GEOMETRY
        geometry_basis = NO_GEOMETRY
    else:
        basin_class = IN_BOUNDARY if basin_name else OUTSIDE
        geometry_basis = GEOMETRY_BASIS
    filed = row["basin_label_filed"]
    if not filed:
        label_class, label_agrees = NOT_LABELLED, None
    elif not basin_name:
        # There is a label and nothing to compare it against, which is a fact about the
        # boundary set rather than a verdict on the label.
        label_class, label_agrees = NO_LABEL, None
    else:
        label_agrees = str(filed).strip().lower() == str(basin_name).strip().lower()
        label_class = AGREES if label_agrees else DISAGREES
    plays = list(row["play_name"] or ())
    # The answering polygon's vintage where one answered, and the consulted set's where none
    # did. Null only under `no_geometry`, where no set was asked and naming one would be a
    # claim about a question nobody put.
    vintage = row["boundary_vintage"] or (set_vintage if basin_class == OUTSIDE else None)
    return {
        "api10": row["api10"],
        "state_code": row["state_code"],
        "basin_name": basin_name if basin_class == IN_BOUNDARY else None,
        "basin_class": basin_class,
        "basin_overlap": int(row["basin_overlap"] or 0),
        "play_name": plays,
        "play_class": PLAYS if plays else NO_PLAY,
        "basin_label_filed": filed,
        "label_class": label_class,
        "label_agrees": label_agrees,
        "boundary_vintage": vintage,
        "geometry_basis": geometry_basis,
        "boundary_id": row["boundary_id"],
        "rule_id": rule_id,
    }


def _canonical_inputs(connection: psycopg.Connection) -> list[InputRef]:
    with connection.cursor() as cursor:
        cursor.execute(_INPUT_DERIVATIONS)
        return [
            InputRef(kind="derivation", ref_id=derivation_id, as_of_vintage=vintage)
            for derivation_id, vintage in cursor.fetchall()
        ]


def refresh_well_basin_context(connection: psycopg.Connection) -> BasinContextRefresh:
    """Rebuild the mart. One row per well in canonical.wells_latest, and no other row."""
    registry = load_jurisdictions(connection)
    # The rule that decided each row, read from the registry rather than mapped here: a
    # jurisdiction that registers no basin_context decision gets a null rule and its rows say
    # so, which is a registry gap a reader can see rather than another state's rule to wear.
    rule_by_prefix = {
        row.identity_prefix: row.rule(BASIN_CONTEXT)
        for row in registry
        if row.identity_prefix is not None
    }

    with connection.cursor() as cursor:
        cursor.execute(_SET_VINTAGE)
        set_vintage = cursor.fetchone()[0]

    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(CONTEXT_QUERY, {"geometry_basis": GEOMETRY_BASIS})
        rows = [
            classify(dict(row), rule_by_prefix.get(str(row["state_code"])), set_vintage)
            for row in cursor.fetchall()
        ]

    inside = sum(1 for row in rows if row["basin_class"] == IN_BOUNDARY)
    outside = sum(1 for row in rows if row["basin_class"] == OUTSIDE)
    absent = sum(1 for row in rows if row["basin_class"] == NO_GEOMETRY)
    disagreeing = sum(1 for row in rows if row["label_class"] == DISAGREES)

    with derive(
        "mart.refresh",
        output=OutputSpec(
            store="postgres",
            dataset=MART,
            partition={"grain": "well"},
            schema_version="1",
        ),
        params={
            "driven_off": "canonical.wells_latest",
            "geometry_basis": GEOMETRY_BASIS,
            "boundary_kinds": ["basin", "play"],
            "basin_pick": "smallest published area containing the point",
            "boundary_set_vintage": set_vintage,
            "absent_class": OUTSIDE,
            # What the run found, so a served class resolves to a run that says it looked.
            "measured": {
                "rows": len(rows),
                "in_published_boundary": inside,
                "outside_published_boundaries": outside,
                "no_geometry": absent,
                "label_disagrees": disagreeing,
            },
        },
        inputs=_canonical_inputs(connection),
        rules=sorted({rule for rule in rule_by_prefix.values() if rule is not None}),
    ) as context:
        context.set_rows(len(rows))
        context.set_output_hash(
            hash_payload(
                {
                    "rows": sorted(
                        (
                            str(row["api10"]),
                            str(row["basin_class"]),
                            str(row["basin_name"] or ""),
                            str(row["label_class"]),
                        )
                        for row in rows
                    )
                }
            )
        )
    derivation_id = context.derivation_id

    with connection.cursor() as cursor:
        cursor.execute(f"delete from {MART}")
        cursor.executemany(
            _INSERT, [{**row, "derivation_id": derivation_id} for row in rows]
        )
    return BasinContextRefresh(
        derivation_id=derivation_id,
        rows=len(rows),
        inside=inside,
        outside=outside,
        no_geometry=absent,
        disagreeing=disagreeing,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Rebuild marts.well_basin_context.")
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
            refresh = refresh_well_basin_context(connection)
        connection.commit()
    print(json.dumps(refresh.as_dict(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
