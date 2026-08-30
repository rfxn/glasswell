"""Refresh the land-grid metrics mart: observed rollups per PLSS unit (M2-3).

Membership is cr_land_agg_membership_1 — lateral midpoint where a lateral exists, surface
hole otherwise, whole-well and observed-only. Liquid is the oil and condensate streams per
cr_nd_liquids_policy_1. Rebuilt, never appended (§3.0.1).
"""

from __future__ import annotations

import argparse
import json
from bisect import bisect_right
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import psycopg

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
from glasswell.lineage.serialization import hash_payload
from glasswell.marts.cumulatives import per_well_cumulative_cte
from glasswell.marts.tiles import METRIC_LAYERS, install_tile_functions

MEMBERSHIP_RULE = "cr_land_agg_membership_2"
LIQUIDS_RULE = "cr_nd_liquids_policy_1"
PUBLISHER_RULE = "cr_blm_plss_publisher_1"

LIQUIDS_BASIS = "oil+condensate"

# The percentile frame the bins are cut on (min/P2/…/P98/max): the P2/P98 clamp is what
# keeps one divide-by-tiny artefact from collapsing the ramp.
BIN_QUANTILES = (0.02, 0.20, 0.40, 0.60, 0.80, 0.98)
UNPAINTED_BIN = -1

# Cut for a PLSS section, which holds a handful of wells. A rollup over a population two
# orders of magnitude larger states its own scale rather than saturating this one.
SECTION_BANDS: tuple[tuple[int, int | None, str], ...] = (
    (0, 0, "0"),
    (1, 2, "1-2"),
    (3, 7, "3-7"),
    (8, None, "8+"),
)

# One anchor per well, one section per well. The universe is every well with a surface
# point (a lateral-only row is invisible — gate-m23 F-E, all TX today). The lateral pick,
# tie-breaks and the surface fallback are the rule's spec, restated nowhere else: newest
# filed geometry first, ties broken by geom_key — 695 ND wells carry >1 lateral row in one
# promotion batch, so created_at alone is plan-dependent (gate-m23 F-A) — and a midpoint
# resolving no section falls back to the surface hole (gate-m23 F-B).
_MEMBERSHIP = """
with lat as (
    select distinct on (api10) api10, geom
      from canonical.well_spatial
     where geom_type = 'lateral'
     order by api10, created_at desc, geom_key),
sp as (
    select distinct on (api10) api10, geom
      from canonical.well_spatial
     where geom_type = 'surface'
     order by api10, created_at desc, geom_key),
anchor as (
    select sp.api10,
           case when lat.geom is null then null
                when GeometryType(ST_LineMerge(lat.geom)) = 'LINESTRING'
                    then ST_LineInterpolatePoint(ST_LineMerge(lat.geom), 0.5)
                else ST_ClosestPoint(lat.geom, ST_Centroid(lat.geom))
           end as midpoint,
           sp.geom as surface
      from sp
      left join lat using (api10)),
by_midpoint as (
    select distinct on (anchor.api10) anchor.api10, unit.land_unit_id, unit.plssid
      from anchor
      join canonical.land_units unit
        on unit.unit_type = 'section' and ST_Intersects(unit.geom, anchor.midpoint)
     order by anchor.api10, unit.land_unit_id),
by_surface as (
    select distinct on (anchor.api10) anchor.api10, unit.land_unit_id, unit.plssid
      from anchor
      join canonical.land_units unit
        on unit.unit_type = 'section' and ST_Intersects(unit.geom, anchor.surface)
     order by anchor.api10, unit.land_unit_id),
member as (
    select * from by_midpoint
    union all
    select by_surface.*
      from by_surface
     where not exists (select 1 from by_midpoint
                        where by_midpoint.api10 = by_surface.api10)),
""" + per_well_cumulative_cte("member")

_SECTION_CELLS = _MEMBERSHIP + """
select member.land_unit_id,
       count(*)::int as well_count,
       count(prod.api10)::int as prod_well_count,
       coalesce(sum(prod.liquid_bbl), 0)::float8 as liquid_cum_bbl,
       coalesce(sum(prod.gas_mcf), 0)::float8 as gas_cum_mcf,
       coalesce(sum(prod.water_bbl), 0)::float8 as water_cum_bbl
  from member
  left join prod using (api10)
 group by member.land_unit_id
"""

_TOWNSHIP_CELLS = _MEMBERSHIP + """
select member.plssid as land_unit_id,
       count(*)::int as well_count,
       count(prod.api10)::int as prod_well_count,
       coalesce(sum(prod.liquid_bbl), 0)::float8 as liquid_cum_bbl,
       coalesce(sum(prod.gas_mcf), 0)::float8 as gas_cum_mcf,
       coalesce(sum(prod.water_bbl), 0)::float8 as water_cum_bbl
  from member
  left join prod using (api10)
 group by member.plssid
"""

# Texas is expected to be wholly unassigned until a TX land grid exists, so the anomaly
# signal is the grid-state count — with the surface fallback it is expected 0 and any
# nonzero is a well the grid cannot hold at all. Widening the grid is a superseding
# membership rule, same as widening the PLSS scope.
GRID_STATE_API_PREFIXES = ("33",)
# The states the PLSS grid covers at all. Kept separate from GRID_STATE_API_PREFIXES on
# purpose: collapsing the two would silence the anomaly alarm that one exists to raise.
GRID_SCOPE_API_PREFIXES: tuple[str, ...] = ("33",)

# Three counters, not two, and the universe is unfiltered. 355,463 Texas surface points are
# already in `anchor`; scoping the universe would have collapsed a served figure to zero while
# describing a scope that has not changed (cr_land_agg_membership_2).
_UNASSIGNED = _MEMBERSHIP + """
select count(*)::int,
       count(*) filter (where left(anchor.api10, 2) = any(%(grid_prefixes)s))::int,
       count(*) filter (where left(anchor.api10, 2) <> all(%(scope_prefixes)s))::int
  from anchor
 where not exists (select 1 from member where member.api10 = anchor.api10)
"""

_INPUT_DERIVATIONS = """
select derivation_id, created_vintage
  from lineage.derivations
 where derivation_id in (
    select derivation_id from canonical.land_units
    union select derivation_id from canonical.wells
    union select derivation_id from canonical.well_spatial
    union select derivation_id from canonical.production_monthly)
 order by derivation_id
"""

_INSERT = """
insert into marts.land_metrics_tile
    (land_unit_id, unit_type, plssid, label, well_count, prod_well_count, liquid_cum_bbl,
     gas_cum_mcf, water_cum_bbl, liquid_bin, bin_edges, bin_population, derivation_id, geom)
select %(land_unit_id)s, unit.unit_type, unit.plssid, unit.label, %(well_count)s,
       %(prod_well_count)s, %(liquid_cum_bbl)s, %(gas_cum_mcf)s, %(water_cum_bbl)s,
       %(liquid_bin)s, %(bin_edges)s, %(bin_population)s, %(derivation_id)s, unit.geom
  from canonical.land_units unit
 where unit.land_unit_id = %(land_unit_id)s
"""


@dataclass(frozen=True, slots=True)
class MetricsRefresh:
    derivation_id: str
    row_counts: Mapping[str, int]
    layers: tuple[str, ...]
    bin_frames: Mapping[str, Mapping[str, object]]
    unassigned_wells: int
    unassigned_grid_state_wells: int
    unassigned_out_of_grid_scope_wells: int = 0

    def to_dict(self) -> dict[str, object]:
        return {
            "derivation_id": self.derivation_id,
            "row_counts": dict(self.row_counts),
            "layers": list(self.layers),
            "bin_frames": {grain: dict(frame) for grain, frame in self.bin_frames.items()},
            "unassigned_wells": self.unassigned_wells,
            "unassigned_grid_state_wells": self.unassigned_grid_state_wells,
            "unassigned_out_of_grid_scope_wells": self.unassigned_out_of_grid_scope_wells,
        }


def percentile(ordered: Sequence[float], quantile: float) -> float:
    """percentile_cont's linear interpolation, restated so the frame is unit-testable."""
    if not ordered:
        raise ValueError("percentile of an empty population")
    position = (len(ordered) - 1) * quantile
    below = int(position)
    above = min(below + 1, len(ordered) - 1)
    fraction = position - below
    return ordered[below] + (ordered[above] - ordered[below]) * fraction


def bin_edges(liquid_values: Sequence[float]) -> list[float]:
    """[min, P2, P20, P40, P60, P80, P98, max] over the cells with observed liquid."""
    ordered = sorted(liquid_values)
    return [ordered[0], *(percentile(ordered, q) for q in BIN_QUANTILES), ordered[-1]]


def liquid_bin(value: float, edges: Sequence[float]) -> int:
    """0..6 for observed liquid — clamped through P2/P98 by construction — else -1."""
    if value <= 0:
        return UNPAINTED_BIN
    return min(bisect_right(list(edges[1:-1]), value), 6)


def support_distribution(
    supports: Sequence[int], bands: Sequence[tuple[int, int | None, str]] = SECTION_BANDS
) -> dict[str, int]:
    """Protocol 4D's support statement. The bands are a parameter because a PLSS section
    holds a handful of wells and a vintage cohort holds hundreds; one scale saturates."""
    classes = {label: 0 for _, _, label in bands}
    for support in supports:
        for low, high, label in bands:
            if low <= support and (high is None or support <= high):
                classes[label] += 1
                break
    return classes


def _cells(connection: psycopg.Connection, sql: str, unit_type: str) -> list[dict[str, object]]:
    with connection.cursor() as cursor:
        cursor.execute(sql)
        columns = [description.name for description in cursor.description]
        rows = [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]
    for row in rows:
        row["unit_type"] = unit_type
    return rows


def _frame(cells: Sequence[dict[str, object]]) -> dict[str, object]:
    liquid = [
        float(cell["liquid_cum_bbl"])  # type: ignore[arg-type]
        for cell in cells
        if float(cell["liquid_cum_bbl"]) > 0  # type: ignore[arg-type]
    ]
    edges = bin_edges(liquid) if liquid else []
    return {
        "edges": edges,
        "population": len(liquid),
        "quantiles": ["min", *[f"p{int(q * 100)}" for q in BIN_QUANTILES], "max"],
        "support_distribution": support_distribution(
            [int(cell["prod_well_count"]) for cell in cells]  # type: ignore[arg-type]
        ),
    }


def refresh_land_metrics(connection: psycopg.Connection) -> MetricsRefresh:
    """Rebuild marts.land_metrics_tile under one content-addressed derivation."""
    sections = _cells(connection, _SECTION_CELLS, "section")
    townships = _cells(connection, _TOWNSHIP_CELLS, "township")
    with connection.cursor() as cursor:
        cursor.execute(
            _UNASSIGNED,
            {
                "grid_prefixes": list(GRID_STATE_API_PREFIXES),
                "scope_prefixes": list(GRID_SCOPE_API_PREFIXES),
            },
        )
        unassigned, unassigned_grid_state, unassigned_out_of_scope = (
            int(count) for count in cursor.fetchone()
        )

    frames = {"section": _frame(sections), "township": _frame(townships)}
    for grain, cells in (("section", sections), ("township", townships)):
        frame = frames[grain]
        edges: Sequence[float] = frame["edges"]  # type: ignore[assignment]
        for cell in cells:
            observed = float(cell["liquid_cum_bbl"])  # type: ignore[arg-type]
            cell["liquid_bin"] = liquid_bin(observed, edges) if edges else UNPAINTED_BIN
            cell["bin_edges"] = json.dumps(edges)
            cell["bin_population"] = frame["population"]

    every = [*townships, *sections]
    fingerprint = hash_payload(
        {"land_metrics_tile": sorted(
            (str(cell["land_unit_id"]), json.dumps(cell, sort_keys=True, default=float))
            for cell in every
        )}
    )

    with derive(
        "mart.refresh",
        output=OutputSpec(
            store="postgis",
            dataset="marts.land_metrics_tile",
            partition={"grid": "nd_plss"},
            schema_version="1",
        ),
        params={
            "layers": [layer.name for layer in METRIC_LAYERS],
            "liquids_basis": LIQUIDS_BASIS,
            "membership": "lateral_midpoint_else_surface",
            "observed_only": True,
            "bin_frames": frames,
            "unassigned_wells": unassigned,
            "unassigned_grid_state_wells": unassigned_grid_state,
            "unassigned_out_of_grid_scope_wells": unassigned_out_of_scope,
            "grid_state_api_prefixes": list(GRID_STATE_API_PREFIXES),
            "grid_scope_api_prefixes": list(GRID_SCOPE_API_PREFIXES),
        },
        inputs=_canonical_inputs(connection),
        rules=[MEMBERSHIP_RULE, LIQUIDS_RULE, PUBLISHER_RULE],
    ) as context:
        context.set_rows(len(every))
        context.set_output_hash(fingerprint)

    # The id is content-addressed and only exists once the block closes, so the rows carrying
    # it are written after it — one transaction, the same shape as the land-units mart.
    with connection.cursor() as cursor:
        cursor.execute("delete from marts.land_metrics_tile")
        cursor.executemany(
            _INSERT,
            [
                {
                    "land_unit_id": cell["land_unit_id"],
                    "well_count": cell["well_count"],
                    "prod_well_count": cell["prod_well_count"],
                    "liquid_cum_bbl": cell["liquid_cum_bbl"],
                    "gas_cum_mcf": cell["gas_cum_mcf"],
                    "water_cum_bbl": cell["water_cum_bbl"],
                    "liquid_bin": cell["liquid_bin"],
                    "bin_edges": cell["bin_edges"],
                    "bin_population": cell["bin_population"],
                    "derivation_id": context.derivation_id,
                }
                for cell in every
            ],
        )
    install_tile_functions(connection)

    session = current_session()
    emit(
        connection,
        "mart.refreshed",
        subject_type="derivation",
        subject_id=context.derivation_id,
        payload={"row_counts": {"land_metrics_tile": len(every)}},
        correlation_id=session.correlation_id,
        occurred_at=session.clock.now(),
    )
    return MetricsRefresh(
        derivation_id=context.derivation_id,
        row_counts={"land_metrics_tile": len(every)},
        layers=tuple(layer.name for layer in METRIC_LAYERS),
        bin_frames=frames,
        unassigned_wells=unassigned,
        unassigned_grid_state_wells=unassigned_grid_state,
        unassigned_out_of_grid_scope_wells=unassigned_out_of_scope,
    )


def _canonical_inputs(connection: psycopg.Connection) -> list[InputRef]:
    with connection.cursor() as cursor:
        cursor.execute(_INPUT_DERIVATIONS)
        return [
            InputRef(kind="derivation", ref_id=derivation_id, as_of_vintage=vintage)
            for derivation_id, vintage in cursor.fetchall()
        ]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Refresh the land-grid metrics mart.")
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--env-id", default=None, help="override the fingerprinted env id")
    parser.add_argument("--code-version", default=None)
    arguments = parser.parse_args(argv)

    with psycopg.connect(arguments.dsn) as connection:
        environment = resolve_environment(
            connection, env_id=arguments.env_id, code_version=arguments.code_version
        )
        with lineage_session(recorder=PostgresRecorder(connection), environment=environment):
            report = refresh_land_metrics(connection)
        connection.commit()
        print(json.dumps(report.to_dict(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
