"""Refresh the land-grid tile mart from canonical.land_units (M1-4).

One mart, two published views: martin serves townships and sections as separate function
sources so each starts at its own zoom floor. Rebuilt, never appended (§3.0.1).
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import psycopg

from glasswell.db.dsn import add_dsn_argument, resolve_dsn
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
from glasswell.marts.tiles import LAND_LAYERS, install_tile_functions

DATUM_RULE = "cr_blm_plss_datum_1"
PUBLISHER_RULE = "cr_blm_plss_publisher_1"
SCOPE_RULE = "cr_blm_plss_scope_1"

_SELECT = """
select unit.land_unit_id, unit.unit_type, unit.plssid, unit.label, unit.geom
  from canonical.land_units unit
"""

_INPUT_DERIVATIONS = """
select derivation_id, created_vintage
  from lineage.derivations
 where derivation_id in (select derivation_id from canonical.land_units)
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


def refresh_land_units(connection: psycopg.Connection) -> MartRefresh:
    """Rebuild marts.land_units_tile under one content-addressed derivation."""
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
            dataset="marts.land_units_tile",
            partition={"grid": "nd_plss"},
            schema_version="1",
        ),
        params={"layers": [layer.name for layer in LAND_LAYERS]},
        inputs=_canonical_inputs(connection),
        rules=[DATUM_RULE, PUBLISHER_RULE, SCOPE_RULE],
    ) as context:
        context.set_rows(rows)
        context.set_output_hash(hash_payload({"land_units_tile": digest}))

    # The id is content-addressed and only exists once the block closes, so the rows carrying
    # it are written after it — one transaction, the same shape as the ingest promotions.
    with connection.cursor() as cursor:
        cursor.execute("delete from marts.land_units_tile")
        cursor.execute(
            "insert into marts.land_units_tile"
            " (land_unit_id, unit_type, plssid, label, geom, derivation_id)"
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
        payload={"row_counts": {"land_units_tile": rows}},
        correlation_id=session.correlation_id,
        occurred_at=session.clock.now(),
    )
    return MartRefresh(
        derivation_id=context.derivation_id,
        row_counts={"land_units_tile": rows},
        layers=tuple(layer.name for layer in LAND_LAYERS),
    )


def _canonical_inputs(connection: psycopg.Connection) -> list[InputRef]:
    with connection.cursor() as cursor:
        cursor.execute(_INPUT_DERIVATIONS)
        return [
            InputRef(kind="derivation", ref_id=derivation_id, as_of_vintage=vintage)
            for derivation_id, vintage in cursor.fetchall()
        ]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Refresh the land-grid tile mart.")
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
            report = refresh_land_units(connection)
        connection.commit()
        print(json.dumps(report.to_dict(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
