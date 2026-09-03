"""Seed the registries the slices read: sources, CRS, conformance rules, glossary."""

from __future__ import annotations

import psycopg

from glasswell.seed.conformance_basin_context import (
    BASIN_CONTEXT_RULES,
    seed_conformance_basin_context,
)
from glasswell.seed.conformance_basins import BASIN_RULES, seed_conformance_basins
from glasswell.seed.conformance_c115b import (
    C115B_RULES,
    seed_conformance_c115b,
    seed_nm_waste_types,
)
from glasswell.seed.conformance_co import CO_RULES, seed_conformance_co
from glasswell.seed.conformance_fracfocus import FRACFOCUS_RULES, seed_conformance_fracfocus
from glasswell.seed.conformance_land import LAND_RULES, seed_conformance_land
from glasswell.seed.conformance_mt import MT_RULES, seed_conformance_mt
from glasswell.seed.conformance_nd import ND_RULES, seed_conformance_nd
from glasswell.seed.conformance_nm import NM_RULES, seed_conformance_nm
from glasswell.seed.conformance_nm_wells import (
    NM_WELLS_GIS_RULES,
    NM_WELLS_RULES,
    seed_conformance_nm_wells,
    seed_conformance_nm_wells_gis,
)
from glasswell.seed.conformance_producing import PRODUCING_RULES, seed_conformance_producing
from glasswell.seed.conformance_schedules import (
    SCHEDULE_RULES,
    seed_conformance_schedules,
)
from glasswell.seed.conformance_status_history import (
    HISTORY_RULE_IDS,
    STATUS_HISTORY,
    seed_conformance_status_history,
)
from glasswell.seed.conformance_tx import TX_RULES, seed_conformance_tx
from glasswell.seed.conformance_typecurve import TYPECURVE_RULES, seed_conformance_typecurve
from glasswell.seed.conformance_vintage import VINTAGE_RULES, seed_conformance_vintage
from glasswell.seed.features import FEATURE_SPECS, FEATURE_VERSION, seed_features
from glasswell.seed.formations_nd import FORMATION_ALIASES, seed_nd_formation_aliases
from glasswell.seed.glossary import GLOSSARY_SEED_PATH, load_glossary_seed, seed_glossary, slug
from glasswell.seed.jurisdictions import (
    JURISDICTION_CODES,
    JURISDICTION_RULES,
    JURISDICTIONS,
    seed_jurisdictions,
)
from glasswell.seed.reference import (
    CRS_ROWS,
    NM_STREAM_ROWS,
    SOURCES,
    seed_crs,
    seed_nm_streams,
    seed_sources,
)
from glasswell.seed.schedules import (
    JOB_SOURCES,
    JOBS,
    REFUSAL_CODES,
    SCHEDULES,
    seed_schedules,
)

__all__ = [
    "BASIN_CONTEXT_RULES",
    "BASIN_RULES",
    "C115B_RULES",
    "CO_RULES",
    "CRS_ROWS",
    "FEATURE_SPECS",
    "FEATURE_VERSION",
    "FORMATION_ALIASES",
    "FRACFOCUS_RULES",
    "GLOSSARY_SEED_PATH",
    "HISTORY_RULE_IDS",
    "JOBS",
    "JOB_SOURCES",
    "JURISDICTIONS",
    "JURISDICTION_CODES",
    "JURISDICTION_RULES",
    "LAND_RULES",
    "MT_RULES",
    "ND_RULES",
    "NM_RULES",
    "NM_STREAM_ROWS",
    "NM_WELLS_GIS_RULES",
    "NM_WELLS_RULES",
    "PRODUCING_RULES",
    "REFUSAL_CODES",
    "SCHEDULES",
    "SCHEDULE_RULES",
    "SOURCES",
    "STATUS_HISTORY",
    "TX_RULES",
    "TYPECURVE_RULES",
    "VINTAGE_RULES",
    "load_glossary_seed",
    "seed_all",
    "seed_conformance_basin_context",
    "seed_conformance_basins",
    "seed_conformance_c115b",
    "seed_conformance_fracfocus",
    "seed_conformance_land",
    "seed_conformance_mt",
    "seed_conformance_nd",
    "seed_conformance_nm",
    "seed_conformance_nm_wells",
    "seed_conformance_nm_wells_gis",
    "seed_conformance_producing",
    "seed_conformance_schedules",
    "seed_conformance_status_history",
    "seed_conformance_tx",
    "seed_conformance_typecurve",
    "seed_conformance_vintage",
    "seed_crs",
    "seed_features",
    "seed_glossary",
    "seed_jurisdictions",
    "seed_nd_formation_aliases",
    "seed_nm_streams",
    "seed_nm_waste_types",
    "seed_schedules",
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
        # First of all, and for the reason the block above gives twice over: one of its five
        # rule ids carries the `cr_tx_` prefix seed_conformance_tx counts on, so seeded after
        # it the first run's number would differ from the second's. It registers the boundary
        # source it is filed under, exactly as the seeder below it does.
        "conformance_rules_basin_context": seed_conformance_basin_context(connection),
        "conformance_rules_tx": seed_conformance_tx(connection),
        "conformance_rules_land": seed_conformance_land(connection),
        "conformance_rules_c115b": seed_conformance_c115b(connection),
        # Registers its own source, so it goes before seed_sources for the reason C-115B does:
        # that seeder's count is a registry total, and a source added after it makes the first
        # run's number differ from the second's. Its rules also carry an nm_ocd_ source id, so
        # it has to precede the NM seeder as well — both constraints point the same way.
        "conformance_rules_nm_wells_gis": seed_conformance_nm_wells_gis(connection),
        # Before seed_sources for the reason TX and land are: it registers the two EIA sources,
        # and the number seed_sources returns is a registry total.
        "conformance_rules_basins": seed_conformance_basins(connection),
        "sources": seed_sources(connection),
        # Straight after seed_sources, which is the first point at which every source a cadence
        # rule can be filed under exists. It goes here rather than last because the four
        # seeders below count by source-id prefix and a cadence rule carries one of those
        # prefixes: seeded after them, the first run's totals would differ from the second's.
        "conformance_rules_schedules": seed_conformance_schedules(connection),
        # After seed_sources, which registers the five ECMC sources these rules are filed
        # under, and before seed_jurisdictions, whose Colorado rule rows FK to them. Its
        # count is over its own ids, so no sibling seeder's total moves when it grows.
        "conformance_rules_co": seed_conformance_co(connection),
        "crs_registry": seed_crs(connection),
        "conformance_rules_fracfocus": seed_conformance_fracfocus(connection),
        # Before the ND seeder for the same reason TX is before everything: these rows carry an
        # nd_ source_id, and the count the ND seeder returns is a registry total over that
        # prefix. Seeded after it, the first run's number would differ from the second's.
        "conformance_rules_producing": seed_conformance_producing(connection),
        # Before the ND seeder for the reason the producing block gives: these rows carry an
        # nd_ source_id and the ND count is a registry total over that prefix.
        "conformance_rules_typecurve": seed_conformance_typecurve(connection),
        # Same reason, same place: this row carries an nd_ source id too, and the ND seeder's
        # count is a registry total over that prefix.
        "conformance_rules_vintage": seed_conformance_vintage(connection),
        "conformance_rules": seed_conformance_nd(connection),
        "formation_aliases_nd": seed_nd_formation_aliases(connection),
        # Before the NM seeder, and for the reason the two comments above give: its rules carry
        # nm_ocd_ source ids and the count seed_conformance_nm returns is a registry total over
        # that prefix. Seeded after it, the first run's number would differ from the second's.
        "conformance_rules_nm_wells": seed_conformance_nm_wells(connection),
        # Same place, same reason: one nm_ocd_wellhistory row. It must also land before
        # seed_jurisdictions, whose rule insert is guarded on the conformance row existing.
        "conformance_rules_status_history": seed_conformance_status_history(connection),
        "conformance_rules_nm": seed_conformance_nm(connection),
        "conformance_rules_mt": seed_conformance_mt(connection),
        "nm_stream_map": seed_nm_streams(connection),
        "nm_waste_type_map": seed_nm_waste_types(connection),
        "glossary_terms": seed_glossary(connection),
        "feature_specs": seed_features(connection),
        # Last: its rule rows FK to lineage.conformance_rules, so every conformance seeder
        # has to have run, and the count it returns is a registry total.
        "jurisdictions": seed_jurisdictions(connection),
        # Last: it FKs to lineage.conformance_rules through every schedule row's rule_id, so
        # the cadence seeder above has to have run, and its count is over its own table.
        "scheduled_jobs": seed_schedules(connection),
    }
