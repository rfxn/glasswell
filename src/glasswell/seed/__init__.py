"""Seed the registries the slices read: sources, CRS, conformance rules, glossary."""

from __future__ import annotations

import psycopg

from glasswell.seed.conformance_c115b import (
    C115B_RULES,
    seed_conformance_c115b,
    seed_nm_waste_types,
)
from glasswell.seed.conformance_fracfocus import FRACFOCUS_RULES, seed_conformance_fracfocus
from glasswell.seed.conformance_land import LAND_RULES, seed_conformance_land
from glasswell.seed.conformance_nd import ND_RULES, seed_conformance_nd
from glasswell.seed.conformance_nm import NM_RULES, seed_conformance_nm
from glasswell.seed.conformance_tx import TX_RULES, seed_conformance_tx
from glasswell.seed.features import FEATURE_SPECS, FEATURE_VERSION, seed_features
from glasswell.seed.formations_nd import FORMATION_ALIASES, seed_nd_formation_aliases
from glasswell.seed.glossary import GLOSSARY_SEED_PATH, load_glossary_seed, seed_glossary, slug
from glasswell.seed.reference import (
    CRS_ROWS,
    NM_STREAM_ROWS,
    SOURCES,
    seed_crs,
    seed_nm_streams,
    seed_sources,
)

__all__ = [
    "C115B_RULES",
    "CRS_ROWS",
    "FEATURE_SPECS",
    "FEATURE_VERSION",
    "FORMATION_ALIASES",
    "FRACFOCUS_RULES",
    "GLOSSARY_SEED_PATH",
    "LAND_RULES",
    "ND_RULES",
    "NM_RULES",
    "NM_STREAM_ROWS",
    "SOURCES",
    "TX_RULES",
    "load_glossary_seed",
    "seed_all",
    "seed_conformance_c115b",
    "seed_conformance_fracfocus",
    "seed_conformance_land",
    "seed_conformance_nd",
    "seed_conformance_nm",
    "seed_conformance_tx",
    "seed_crs",
    "seed_features",
    "seed_glossary",
    "seed_nd_formation_aliases",
    "seed_nm_streams",
    "seed_nm_waste_types",
    "seed_sources",
    "slug",
]


def seed_all(connection: psycopg.Connection) -> dict[str, int]:
    """Idempotent: P7 runs it against a database that may already carry every row."""
    # TX and land first, and not for taste: each registers its own sources, and the counts the
    # ND seeders return are registry totals. Seeding either after them makes the first run's
    # numbers differ from the second's, which is the only thing the idempotence check has to
    # go on.
    return {
        "conformance_rules_tx": seed_conformance_tx(connection),
        "conformance_rules_land": seed_conformance_land(connection),
        "conformance_rules_c115b": seed_conformance_c115b(connection),
        "sources": seed_sources(connection),
        "crs_registry": seed_crs(connection),
        "conformance_rules_fracfocus": seed_conformance_fracfocus(connection),
        "conformance_rules": seed_conformance_nd(connection),
        "formation_aliases_nd": seed_nd_formation_aliases(connection),
        "conformance_rules_nm": seed_conformance_nm(connection),
        "nm_stream_map": seed_nm_streams(connection),
        "nm_waste_type_map": seed_nm_waste_types(connection),
        "glossary_terms": seed_glossary(connection),
        "feature_specs": seed_features(connection),
    }
