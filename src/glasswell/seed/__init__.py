"""Seed the registries the slices read: sources, CRS, conformance rules, glossary."""

from __future__ import annotations

import psycopg

from glasswell.seed.conformance_land import LAND_RULES, seed_conformance_land
from glasswell.seed.conformance_nd import ND_RULES, seed_conformance_nd
from glasswell.seed.conformance_nm import NM_RULES, seed_conformance_nm
from glasswell.seed.conformance_tx import TX_RULES, seed_conformance_tx
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
    "CRS_ROWS",
    "GLOSSARY_SEED_PATH",
    "LAND_RULES",
    "ND_RULES",
    "NM_RULES",
    "NM_STREAM_ROWS",
    "SOURCES",
    "TX_RULES",
    "load_glossary_seed",
    "seed_all",
    "seed_conformance_land",
    "seed_conformance_nd",
    "seed_conformance_nm",
    "seed_conformance_tx",
    "seed_crs",
    "seed_glossary",
    "seed_nm_streams",
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
        "sources": seed_sources(connection),
        "crs_registry": seed_crs(connection),
        "conformance_rules": seed_conformance_nd(connection),
        "conformance_rules_nm": seed_conformance_nm(connection),
        "nm_stream_map": seed_nm_streams(connection),
        "glossary_terms": seed_glossary(connection),
    }
