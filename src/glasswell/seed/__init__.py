"""Seed the registries the slices read: sources, CRS, conformance rules, glossary."""

from __future__ import annotations

import psycopg

from glasswell.seed.conformance_nd import ND_RULES, seed_conformance_nd
from glasswell.seed.conformance_tx import TX_RULES, seed_conformance_tx
from glasswell.seed.glossary import GLOSSARY_SEED_PATH, load_glossary_seed, seed_glossary, slug
from glasswell.seed.reference import CRS_ROWS, SOURCES, seed_crs, seed_sources

__all__ = [
    "CRS_ROWS",
    "GLOSSARY_SEED_PATH",
    "ND_RULES",
    "SOURCES",
    "TX_RULES",
    "load_glossary_seed",
    "seed_all",
    "seed_conformance_nd",
    "seed_conformance_tx",
    "seed_crs",
    "seed_glossary",
    "seed_sources",
    "slug",
]


def seed_all(connection: psycopg.Connection) -> dict[str, int]:
    """Idempotent: P7 runs it against a database that may already carry every row."""
    # TX first, and not for taste: it registers its own sources, and the counts the ND seeders
    # return are registry totals. Seeding it after them makes the first run's numbers differ
    # from the second's, which is the only thing the idempotence check has to go on.
    return {
        "conformance_rules_tx": seed_conformance_tx(connection),
        "sources": seed_sources(connection),
        "crs_registry": seed_crs(connection),
        "conformance_rules": seed_conformance_nd(connection),
        "glossary_terms": seed_glossary(connection),
    }
