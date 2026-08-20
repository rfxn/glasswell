"""Seed the registries the ND slice reads: sources, CRS, conformance rules, glossary."""

from __future__ import annotations

import psycopg

from glasswell.seed.conformance_nd import ND_RULES, seed_conformance_nd
from glasswell.seed.glossary import GLOSSARY_SEED_PATH, load_glossary_seed, seed_glossary, slug
from glasswell.seed.reference import CRS_ROWS, SOURCES, seed_crs, seed_sources

__all__ = [
    "CRS_ROWS",
    "GLOSSARY_SEED_PATH",
    "ND_RULES",
    "SOURCES",
    "load_glossary_seed",
    "seed_all",
    "seed_conformance_nd",
    "seed_crs",
    "seed_glossary",
    "seed_sources",
    "slug",
]


def seed_all(connection: psycopg.Connection) -> dict[str, int]:
    """Idempotent: P7 runs it against a database that may already carry every row."""
    return {
        "sources": seed_sources(connection),
        "crs_registry": seed_crs(connection),
        "conformance_rules": seed_conformance_nd(connection),
        "glossary_terms": seed_glossary(connection),
    }
