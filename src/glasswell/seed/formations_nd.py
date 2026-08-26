"""Reviewed ND MPR pool aliases for the fv1.0 formation-group feature."""

from __future__ import annotations

from datetime import date

import psycopg

EFFECTIVE_FROM = date(2026, 8, 26)

# Exact source labels measured from all current nd_mpr_xlsx production rows on 2026-08-26.
# Composite labels stay composite unless the source wording supports a lossless rollup.
FORMATION_ALIASES: tuple[tuple[str, str, str, str], ...] = (
    ("BAKKEN", "bakken", "bakken", "1.000"),
    ("MADISON", "madison", "madison", "1.000"),
    ("SANISH", "sanish", "sanish", "1.000"),
    ("RED RIVER", "red_river", "red_river", "1.000"),
    ("PIERRE", "pierre", "pierre", "1.000"),
    ("SOUTH RED RIVER B", "red_river_b", "red_river", "0.950"),
    ("DUPEROW", "duperow", "duperow", "1.000"),
    ("SPEARFISH/CHARLES", "spearfish_charles", "spearfish_charles", "0.900"),
    ("SPEARFISH", "spearfish", "spearfish", "1.000"),
    ("NORTH RED RIVER B", "red_river_b", "red_river", "0.950"),
    ("BIRDBEAR", "birdbear", "birdbear", "1.000"),
    ("DEVONIAN", "devonian", "__other__", "1.000"),
    ("TYLER", "tyler", "__other__", "1.000"),
    ("SILURIAN", "silurian", "__other__", "1.000"),
    ("BAKKEN/THREE FORKS", "bakken_three_forks", "__other__", "1.000"),
    ("SPEARFISH/MADISON", "spearfish_madison", "__other__", "1.000"),
    ("ORDOVICIAN", "ordovician", "__other__", "1.000"),
    ("STONEWALL", "stonewall", "__other__", "1.000"),
    ("HEATH", "heath", "__other__", "1.000"),
    ("MIDALE/NESSON", "midale_nesson", "__other__", "1.000"),
    ("LODGEPOLE", "lodgepole", "__other__", "1.000"),
    ("RED RIVER B", "red_river_b", "red_river", "0.950"),
    ("WEST RED RIVER", "red_river", "red_river", "0.950"),
    ("WINNIPEGOSIS", "winnipegosis", "__other__", "1.000"),
    ("DAKOTA", "dakota", "__other__", "1.000"),
    ("RED RIVER UNIT", "red_river", "red_river", "0.950"),
    ("DAWSON BAY", "dawson_bay", "__other__", "1.000"),
    ("WINNIPEG/DEADWOOD", "winnipeg_deadwood", "__other__", "1.000"),
    ("RATCLIFFE", "ratcliffe", "__other__", "1.000"),
    ("THREE FORKS", "three_forks", "three_forks", "1.000"),
    ("TYLER A", "tyler_a", "__other__", "1.000"),
    ("MINNELUSA", "minnelusa", "__other__", "1.000"),
    ("CAMBRO/ORDOVICIAN", "cambro_ordovician", "__other__", "1.000"),
    ("GUNTON", "gunton", "__other__", "1.000"),
    ("WINNIPEG", "winnipeg", "__other__", "1.000"),
    ("DEADWOOD", "deadwood", "__other__", "1.000"),
    ("Dakota", "dakota", "__other__", "1.000"),
    ("MISSION CANYON", "mission_canyon", "__other__", "1.000"),
    ("SOURIS RIVER", "souris_river", "__other__", "1.000"),
    ("UnknownXML", "unknown", "__other__", "1.000"),
)

_INSERT = """
insert into lineage.formation_aliases
    (formation_raw, formation, formation_group, confidence, effective_from, source_id,
     created_vintage)
values (%s, %s, %s, %s, %s, 'nd_mpr_xlsx', %s)
on conflict do nothing
"""


def seed_nd_formation_aliases(connection: psycopg.Connection) -> int:
    with connection.cursor() as cursor:
        cursor.executemany(
            _INSERT,
            [(*row, EFFECTIVE_FROM, EFFECTIVE_FROM) for row in FORMATION_ALIASES],
        )
        cursor.execute(
            "select count(*) from lineage.formation_aliases where source_id = 'nd_mpr_xlsx'"
        )
        return int(cursor.fetchone()[0])
