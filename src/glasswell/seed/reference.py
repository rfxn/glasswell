"""Source registry and CRS reference rows. register_manifest has an FK to sources."""

from __future__ import annotations

from datetime import date

import psycopg

ND_LICENSE_NOTE = "Free GIS download, NAD83, standard ND accuracy disclaimer"

SOURCES: tuple[dict[str, object], ...] = (
    {
        "source_id": "nd_mpr_xlsx",
        "name": "ND DMR monthly production report (XLSX)",
        "jurisdiction": "ND",
        "license_note": (
            "No stated license or redistribution restriction on the free MPR path; standard ND"
            " accuracy disclaimer only. Subscription ToS does not attach to these files."
        ),
        "redistributable": False,
    },
    {
        "source_id": "nd_gis_wells",
        "name": "ND DMR GIS well points (OGD_Wells)",
        "jurisdiction": "ND",
        "license_note": ND_LICENSE_NOTE,
        "redistributable": False,
    },
    {
        "source_id": "nd_gis_horizontals_line",
        "name": "ND DMR GIS lateral centrelines (OGD_Horizontals_Line)",
        "jurisdiction": "ND",
        "license_note": ND_LICENSE_NOTE,
        "redistributable": False,
    },
    {
        "source_id": "nd_gis_spacing_units",
        "name": "ND DMR GIS drilling spacing units (OGD_DrillingSpacingUnits)",
        "jurisdiction": "ND",
        "license_note": ND_LICENSE_NOTE,
        "redistributable": False,
    },
)

CRS_ROWS: tuple[dict[str, object], ...] = (
    {
        "basin": "williston",
        "compute_epsg": 32614,
        "storage_epsg": 4326,
        "effective_from": date(2026, 1, 1),
        "note": (
            "UTM 14N for area and spacing work only. The Williston basin spans zones 13N and"
            " 14N, so lateral length is measured geodesically under cr_nd_compute_crs_2 rather"
            " than projected into either (fp-audit A3-F1)."
        ),
    },
)

_INSERT_SOURCE = """
insert into lineage.sources (source_id, name, jurisdiction, license_note, redistributable)
values (%(source_id)s, %(name)s, %(jurisdiction)s, %(license_note)s, %(redistributable)s)
on conflict do nothing
"""

_INSERT_CRS = """
insert into lineage.crs_registry (basin, compute_epsg, storage_epsg, effective_from, note)
values (%(basin)s, %(compute_epsg)s, %(storage_epsg)s, %(effective_from)s, %(note)s)
on conflict do nothing
"""


def seed_sources(connection: psycopg.Connection) -> int:
    with connection.cursor() as cursor:
        cursor.executemany(_INSERT_SOURCE, SOURCES)
        cursor.execute("select count(*) from lineage.sources")
        return int(cursor.fetchone()[0])


def seed_crs(connection: psycopg.Connection) -> int:
    with connection.cursor() as cursor:
        cursor.executemany(_INSERT_CRS, CRS_ROWS)
        cursor.execute("select count(*) from lineage.crs_registry")
        return int(cursor.fetchone()[0])
