"""Source registry and CRS reference rows. register_manifest has an FK to sources."""

from __future__ import annotations

from datetime import date

import psycopg

ND_LICENSE_NOTE = "Free GIS download, NAD83, standard ND accuracy disclaimer"
# The disclaimer itself, quoted from the <useconst> element of OGD_Directionals.shp.xml inside
# the archive rather than paraphrased from the download page — the shipped metadata is the copy
# that travels with the bytes, so it is the one a manifest can be checked against. It is a
# warranty disclaimer and grants nothing, which is why redistributable stays False.
ND_SURVEY_LICENSE_NOTE = (
    "Disclaimer only; no grant. Verbatim from OGD_Directionals.shp.xml <useconst>: “Although"
    " we try to keep this information up-to-date and accurate, neither the State of North"
    " Dakota, nor any agency, officer, or employee of the State of North Dakota warrants the"
    " accuracy, reliability or timeliness of any information published by this system, nor"
    " endorses any content, viewpoints, products, or services linked from this system, and"
    " shall not be held responsible for any losses caused by reliance on the accuracy,"
    " reliability or timeliness of such information. Portions of such information may be"
    " incorrect or out of date. Any person or entity that relies on any information obtained"
    " from this system does so at his or her own risk.” <accconst>: “The State of"
    " North Dakota makes every effort to provide virus-free files but does not guarantee"
    " uncorrupted files”. Coverage caveat: the public extracts are served through"
    " non-confidential views (the geodatabase catalog exposes directionals_confidential and"
    " vw_SDE_GetNonConDirSurveys_Layer), so confidential-well surveys are excluded by"
    " construction. Redundancy finding: NDOGD_Surveys.gdb.zip is 313.6 MB and holds exactly"
    " OGD_Directionals and OGD_Horizontals plus editor-tracking columns, so it is not fetched"
    " (data-sources-wellops.md §4.2)."
)
# The honest note, and it stays honest: absence of a restriction is not a grant, so every NM
# manifest carries redistributable = False until someone publishes terms (SB-01 §1.3).
NM_LICENSE_NOTE = (
    "UNVERIFIED. No published licence, ToS or redistribution grant on the OCD Data or FTP"
    " pages. Absence of a restriction is not a grant; NM data is never described as open"
    " licensed."
)

NM_TABLES: tuple[tuple[str, str], ...] = (
    ("wcproduction", "well-completion monthly volumes"),
    ("wellhistory", "well header history"),
    ("wchistory", "well-completion history"),
    ("podwc", "POD to well-completion crosswalk"),
    ("pod", "pooled development units"),
    ("ogrid", "operator registry"),
    ("pool", "pool registry"),
    ("spacingunit", "spacing units"),
    ("property", "properties"),
)

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
    {
        "source_id": "nd_gis_directionals",
        "name": "ND DMR GIS directional survey stations (OGD_Directionals)",
        "jurisdiction": "ND",
        "license_note": ND_SURVEY_LICENSE_NOTE,
        "redistributable": False,
    },
    {
        "source_id": "fracfocus_csv",
        "name": "FracFocus bulk CSV disclosure archive",
        "jurisdiction": "US",
        "license_note": (
            "FracFocus Terms and Conditions are fetched and hashed for every acquisition."
            " Raw bytes remain unaltered; transformed canonical rows retain source lineage."
            " Redistribution is not asserted."
        ),
        "redistributable": False,
    },
    *(
        {
            "source_id": f"nm_ocd_{table}",
            "name": f"NM OCD {description} ({table})",
            "jurisdiction": "NM",
            "license_note": NM_LICENSE_NOTE,
            "redistributable": False,
        }
        for table, description in NM_TABLES
    ),
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

# prd_knd_cde, trimmed of its CHAR(2) padding by cr_nm_wcproduction_pad_1. All four codes are
# seeded although 'C' has no row inside the promotion window: it was measured on 3,398 records
# of 1986-1993, and a vocabulary seeded from the window would quarantine every one of them on
# the day the window widened (cr_nm_wcproduction_stream_vocab_1).
NM_STREAM_ROWS: tuple[dict[str, object], ...] = (
    {"stream_raw": "C", "stream_canonical": "condensate", "promoted": True},
    {"stream_raw": "G", "stream_canonical": "gas", "promoted": True},
    {"stream_raw": "O", "stream_canonical": "oil", "promoted": True},
    {"stream_raw": "W", "stream_canonical": "water", "promoted": True},
)

_INSERT_SOURCE = """
insert into lineage.sources (source_id, name, jurisdiction, license_note, redistributable)
values (%(source_id)s, %(name)s, %(jurisdiction)s, %(license_note)s, %(redistributable)s)
on conflict do nothing
"""

_INSERT_NM_STREAM = """
insert into lineage.nm_stream_map (stream_raw, stream_canonical, promoted)
values (%(stream_raw)s, %(stream_canonical)s, %(promoted)s)
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


def seed_nm_streams(connection: psycopg.Connection) -> int:
    with connection.cursor() as cursor:
        cursor.executemany(_INSERT_NM_STREAM, NM_STREAM_ROWS)
        cursor.execute("select count(*) from lineage.nm_stream_map")
        return int(cursor.fetchone()[0])


def seed_crs(connection: psycopg.Connection) -> int:
    with connection.cursor() as cursor:
        cursor.executemany(_INSERT_CRS, CRS_ROWS)
        cursor.execute("select count(*) from lineage.crs_registry")
        return int(cursor.fetchone()[0])
