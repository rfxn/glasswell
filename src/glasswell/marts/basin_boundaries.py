"""Refresh the boundary tile mart from canonical.basin_boundaries.

One mart, two published views: martin serves basins and plays as separate function sources so
a play surface never draws as a basin. Rebuilt, never appended (§3.0.1).
"""

from __future__ import annotations

import argparse
import json
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
from glasswell.marts.tiles import BASIN_LAYERS, install_tile_functions

AREA_RULE = "cr_eia_area_provenance_1"
DATUM_RULE = "cr_eia_boundary_datum_1"
LINK_RULE = "cr_eia_basin_link_1"
MEMBERSHIP_RULE = "cr_eia_well_membership_1"
OVERLAP_RULE = "cr_eia_boundary_overlap_1"
PUBLISHER_RULE = "cr_eia_boundary_publisher_1"
REPAIR_RULE = "cr_eia_geometry_repair_1"
TAXONOMY_RULE = "cr_eia_boundary_taxonomy_1"

# The area is the publisher's, rounded and never recomputed (cr_eia_area_provenance_1); two
# decimals because more digits would claim a precision the published figure does not carry.
_SELECT = """
select boundary.boundary_id, boundary.boundary_kind, boundary.name, boundary.basin_name,
       boundary.basin_boundary_id, boundary.sub_basin, boundary.lithology, boundary.age_shale,
       round(boundary.area_sq_mi::numeric, 2)::double precision as area_sq_mi,
       boundary.area_basis, boundary.vintage_label, boundary.geometry_repair, boundary.geom
  from canonical.basin_boundaries boundary
"""

_INPUT_DERIVATIONS = """
select derivation_id, created_vintage
  from lineage.derivations
 where derivation_id in (select derivation_id from canonical.basin_boundaries)
 order by derivation_id
"""


@dataclass(frozen=True, slots=True)
class MartRefresh:
    derivation_id: str
    row_counts: Mapping[str, int]
    layers: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "derivation_id": self.derivation_id,
            "row_counts": dict(self.row_counts),
            "layers": list(self.layers),
        }


def refresh_basin_boundaries(connection: psycopg.Connection) -> MartRefresh:
    """Rebuild marts.basin_boundaries_tile under one content-addressed derivation."""
    with connection.cursor() as cursor:
        cursor.execute(
            "select count(*), coalesce(md5(string_agg(digest, ',' order by digest)), '')"
            f"  from (select md5(p::text) as digest from ({_SELECT}) p) fingerprint"
        )
        rows, digest = cursor.fetchone()

    with derive(
        "mart.refresh",
        output=OutputSpec(
            store="postgis",
            dataset="marts.basin_boundaries_tile",
            partition={"boundaries": "eia_lower48"},
            schema_version="1",
        ),
        params={"layers": [layer.name for layer in BASIN_LAYERS], "area_basis_source": "canonical"},
        inputs=_canonical_inputs(connection),
        rules=[
            AREA_RULE, DATUM_RULE, LINK_RULE, MEMBERSHIP_RULE, OVERLAP_RULE, PUBLISHER_RULE,
            REPAIR_RULE, TAXONOMY_RULE,
        ],
    ) as context:
        context.set_rows(rows)
        context.set_output_hash(hash_payload({"basin_boundaries_tile": digest}))

    # The id is content-addressed and only exists once the block closes, so the rows carrying
    # it are written after it — one transaction, the same shape as the ingest promotions.
    with connection.cursor() as cursor:
        cursor.execute("delete from marts.basin_boundaries_tile")
        cursor.execute(
            "insert into marts.basin_boundaries_tile"
            " (boundary_id, boundary_kind, name, basin_name, basin_boundary_id, sub_basin,"
            "  lithology, age_shale, area_sq_mi, area_basis, vintage_label, geometry_repair,"
            "  geom, derivation_id)"
            f" select p.*, %(derivation_id)s from ({_SELECT}) p",
            {"derivation_id": context.derivation_id},
        )
    install_tile_functions(connection)

    session = current_session()
    emit(
        connection,
        "mart.refreshed",
        subject_type="derivation",
        subject_id=context.derivation_id,
        payload={"row_counts": {"basin_boundaries_tile": rows}},
        correlation_id=session.correlation_id,
        occurred_at=session.clock.now(),
    )
    return MartRefresh(
        derivation_id=context.derivation_id,
        row_counts={"basin_boundaries_tile": rows},
        layers=tuple(layer.name for layer in BASIN_LAYERS),
    )


def _canonical_inputs(connection: psycopg.Connection) -> list[InputRef]:
    with connection.cursor() as cursor:
        cursor.execute(_INPUT_DERIVATIONS)
        return [
            InputRef(kind="derivation", ref_id=derivation_id, as_of_vintage=vintage)
            for derivation_id, vintage in cursor.fetchall()
        ]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Refresh the basin and play boundary mart.")
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--env-id", default=None, help="override the fingerprinted env id")
    parser.add_argument("--code-version", default=None)
    arguments = parser.parse_args(argv)

    with psycopg.connect(arguments.dsn) as connection:
        environment = resolve_environment(
            connection, env_id=arguments.env_id, code_version=arguments.code_version
        )
        with lineage_session(recorder=PostgresRecorder(connection), environment=environment):
            report = refresh_basin_boundaries(connection)
        connection.commit()
        print(json.dumps(report.to_dict(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
