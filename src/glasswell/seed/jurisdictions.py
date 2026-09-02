"""The jurisdiction registry as rows: the same registrations the migration ships, mirrored.

Two writers on purpose. A registry the serving path depends on must ship with its rows, so the
migration carries them and `glasswell-migrate` alone yields a database that serves. And
`scripts/deploy.sh` runs `seed_all` on every deploy, between migrate and the API restart, so a
registration appended in a later release without a migration of its own still lands.
`tests/contract/test_jurisdiction_parity.py` holds the two copies to each other.
"""

from __future__ import annotations

from datetime import date

import psycopg

# Valid time and knowledge time of the founding registrations. The integrator repoints this
# beside the evidence pair, per the REPOINT CHECKLIST at the head of the migration.
REGISTERED_ON = date(2026, 9, 2)
EVIDENCE_TAG = "v0.76"
EVIDENCE_COMMIT = "6f2e9e6e97952000985568e6aa04d479ec84fe83"

# The one decision no registration may be without: a jurisdiction whose status vocabulary is
# unregistered has no rule to cite for the class every well on the map is drawn by.
REQUIRED_DECISIONS = ("status_vocabulary",)

# Exactly one registration carries explorer_default, and it is a fact about the data rather
# than a preference: the explorer opens on the jurisdiction whose production history it can
# actually walk. A partial unique index holds it to one per registration instant; the resolved
# set is the wider claim, and test_jurisdiction_parity.py is what makes it.
EXPLORER_DEFAULT_CODE = "ND"

SHARED_STATUS_DETAIL = "Current effective-dated well entities, not accumulated source revisions."

JURISDICTION_CODES: tuple[dict[str, object], ...] = (
    {"jurisdiction_code": "ND", "level": "state"},
    {"jurisdiction_code": "TX", "level": "state"},
    {"jurisdiction_code": "NM", "level": "state"},
    {"jurisdiction_code": "MT", "level": "state"},
)

JURISDICTIONS: tuple[dict[str, object], ...] = (
    {
        "jurisdiction_code": "ND",
        "name": "North Dakota",
        "regulator_name": "ND Dept. of Mineral Resources, Oil and Gas Division",
        "regulator_url": "https://www.dmr.nd.gov/oilgas/mprindex.asp",
        "identity_prefix": "33",
        "source_ids": (
            "nd_mpr_xlsx",
            "nd_gis_wells",
            "nd_gis_horizontals_line",
            "nd_gis_spacing_units",
            "nd_gis_directionals",
            "blm_plss_townships",
            "blm_plss_sections",
        ),
        "liquids_basis": "oil+condensate",
        "wells_tile_layer_id": "nd_wells",
        "map_colour": "#3FA55E",
        "neighbors_available": True,
        "explorer_default": True,
        "land_grid_state": True,
        "land_grid_scope": True,
        "status_dataset_detail": SHARED_STATUS_DETAIL,
        "rationale": (
            "The founding jurisdiction: NDIC DMR files the monthly production report and the"
            " GIS layers the spine was built on. The two BLM PLSS layers are registered here"
            " because ND is the extent they were loaded for, which is what"
            " lineage.sources.jurisdiction records. It carries explorer_default because it is"
            " the only jurisdiction serving well-grain production history end to end, which is"
            " what the explorer opens on rather than an alphabetical accident."
        ),
    },
    {
        "jurisdiction_code": "TX",
        "name": "Texas",
        "regulator_name": "Railroad Commission of Texas",
        "regulator_url": (
            "https://www.rrc.texas.gov/resource-center/research/data-sets-available-for-download/"
        ),
        "identity_prefix": "42",
        "source_ids": ("tx_gis_wells_county", "tx_wellbore_ewa_csv"),
        "liquids_basis": None,
        "wells_tile_layer_id": "tx_wells",
        "map_colour": "#7C8B96",
        "neighbors_available": False,
        "explorer_default": False,
        "land_grid_state": False,
        "land_grid_scope": False,
        "status_dataset_detail": SHARED_STATUS_DETAIL,
        "rationale": (
            "Served from the RRC county GIS layers and the Wellbore Query export. Texas files"
            " production at the lease, so no liquids basis and no pool-rollup decision are"
            " registered and the API serves cr_tx_allocation_scope_1's disclosure instead of an"
            " empty series."
        ),
    },
    {
        "jurisdiction_code": "NM",
        "name": "New Mexico",
        "regulator_name": "New Mexico EMNRD Oil Conservation Division",
        "regulator_url": "https://www.emnrd.nm.gov/ocd/ocd-data/",
        "identity_prefix": "30",
        "source_ids": (
            "nm_ocd_wcproduction",
            "nm_ocd_wellhistory",
            "nm_ocd_wchistory",
            "nm_ocd_podwc",
            "nm_ocd_pod",
            "nm_ocd_ogrid",
            "nm_ocd_pool",
            "nm_ocd_spacingunit",
            "nm_ocd_property",
            "nm_ocd_wells_gis",
            "nm_c115b_upstream",
        ),
        "liquids_basis": "oil",
        "wells_tile_layer_id": "nm_wells",
        "map_colour": "#3FA55E",
        "neighbors_available": False,
        "explorer_default": False,
        "land_grid_state": False,
        "land_grid_scope": False,
        "status_dataset_detail": SHARED_STATUS_DETAIL,
        "rationale": (
            "Served from the OCD FTP tables, the public wells layer and the C-115B waste"
            " service. The status class is resolved at read time rather than written by the"
            " promotion, and condensate is filed as its own stream, so the liquids basis is oil"
            " alone."
        ),
    },
    {
        "jurisdiction_code": "MT",
        "name": "Montana",
        "regulator_name": "Montana DNRC Board of Oil and Gas Conservation",
        "regulator_url": "https://bogfiles.dnrc.mt.gov",
        "identity_prefix": "25",
        "source_ids": (
            "mt_gis_wells",
            "mt_gis_well_paths",
            "mt_bogc_well_production",
            "mt_bogc_pru_production",
        ),
        "liquids_basis": "oil+condensate",
        "wells_tile_layer_id": "mt_wells",
        "map_colour": "#7C8B96",
        "neighbors_available": True,
        "explorer_default": False,
        "land_grid_state": False,
        "land_grid_scope": False,
        "status_dataset_detail": (
            "Headers only for the statuses cr_mt_gis_status_vocab_1 promotes; the six it does"
            " not quarantine as unknown_status, so this is below the surface-point count and"
            " the difference is in the quarantine ledger, not lost."
        ),
        "rationale": (
            "Served from the MBOGC GIS layers and the two historical production files. The PRU"
            " file reports at lease grain, so its inventory rule is registered and not serving;"
            " the well paths are cartographic centrelines, which is why length has its own"
            " scope decision."
        ),
    },
)

JURISDICTION_RULES: tuple[dict[str, object], ...] = (
    {"jurisdiction_code": "ND", "decision": "status_vocabulary",
     "rule_id": "cr_nd_status_vocab_1"},
    {"jurisdiction_code": "ND", "decision": "geometry_provenance",
     "rule_id": "cr_nd_geometry_provenance_1"},
    {"jurisdiction_code": "ND", "decision": "liquids", "rule_id": "cr_nd_liquids_policy_1"},
    {"jurisdiction_code": "ND", "decision": "production_grain",
     "rule_id": "cr_nd_pool_rollup_1"},
    {"jurisdiction_code": "ND", "decision": "inventory_jurisdiction",
     "rule_id": "cr_nd_inventory_jurisdiction_1"},
    {"jurisdiction_code": "ND", "decision": "identity", "rule_id": "cr_nd_api_identity_1"},
    {"jurisdiction_code": "TX", "decision": "status_vocabulary",
     "rule_id": "cr_tx_status_vocab_1"},
    {"jurisdiction_code": "TX", "decision": "identity", "rule_id": "cr_tx_api10_build_1"},
    {"jurisdiction_code": "TX", "decision": "absence:operator",
     "rule_id": "cr_tx_operator_absence_1"},
    # _2 rather than the _1 the spec table names: the successor is what serves on this base, and
    # a registry naming a superseded rule would be a false claim on the day it is written.
    {"jurisdiction_code": "NM", "decision": "status_vocabulary",
     "rule_id": "cr_nm_wellhistory_status_vocab_2"},
    {"jurisdiction_code": "NM", "decision": "geometry_provenance",
     "rule_id": "cr_nm_wellhistory_geometry_provenance_1"},
    {"jurisdiction_code": "NM", "decision": "liquids",
     "rule_id": "cr_nm_wcproduction_liquids_1"},
    {"jurisdiction_code": "NM", "decision": "production_grain",
     "rule_id": "cr_nm_wcproduction_pool_rollup_1"},
    {"jurisdiction_code": "NM", "decision": "inventory_jurisdiction",
     "rule_id": "cr_nm_wcproduction_inventory_jurisdiction_1"},
    {"jurisdiction_code": "NM", "decision": "identity", "rule_id": "cr_nm_wchistory_api10_1"},
    {"jurisdiction_code": "MT", "decision": "status_vocabulary",
     "rule_id": "cr_mt_gis_status_vocab_1"},
    {"jurisdiction_code": "MT", "decision": "geometry_provenance",
     "rule_id": "cr_mt_paths_geometry_class_1"},
    {"jurisdiction_code": "MT", "decision": "liquids", "rule_id": "cr_mt_liquids_policy_1"},
    {"jurisdiction_code": "MT", "decision": "inventory_jurisdiction",
     "rule_id": "cr_mt_inventory_jurisdiction_1"},
    {"jurisdiction_code": "MT", "decision": "inventory_jurisdiction",
     "rule_id": "cr_mt_pru_inventory_jurisdiction_1", "serving": False,
     "note": "PRU lease grain"},
    {"jurisdiction_code": "MT", "decision": "length_scope",
     "rule_id": "cr_mt_paths_length_scope_1"},
    {"jurisdiction_code": "MT", "decision": "absence:operator",
     "rule_id": "cr_mt_operator_absence_1"},
)

PREFIXES = frozenset(str(row["identity_prefix"]) for row in JURISDICTIONS)
CODES = frozenset(str(row["jurisdiction_code"]) for row in JURISDICTIONS)
NAMES = frozenset(str(row["name"]) for row in JURISDICTIONS)


def identity_pattern(prefix: str) -> str:
    """The literal `045_nd_neighbors.sql` embeds, spelled once and carried as data."""
    return f"^{prefix}[0-9]{{8}}$"


_INSERT_CODE = """
insert into lineage.jurisdiction_codes (jurisdiction_code, level)
values (%(jurisdiction_code)s, %(level)s)
on conflict do nothing
"""

_INSERT_JURISDICTION = """
insert into lineage.jurisdictions (
    jurisdiction_code, effective_from, published_at, evidence_tag, evidence_commit,
    name, regulator_name, regulator_url, identity_scheme, identity_is_unique,
    identity_prefix, identity_pattern, source_ids, liquids_basis, wells_tile_layer_id,
    map_colour, neighbors_available, explorer_default, land_grid_state, land_grid_scope,
    status_dataset_detail, rationale)
values (
    %(jurisdiction_code)s, %(effective_from)s, %(published_at)s, %(evidence_tag)s,
    %(evidence_commit)s, %(name)s, %(regulator_name)s, %(regulator_url)s, %(identity_scheme)s,
    %(identity_is_unique)s, %(identity_prefix)s, %(identity_pattern)s, %(source_ids)s,
    %(liquids_basis)s, %(wells_tile_layer_id)s, %(map_colour)s, %(neighbors_available)s,
    %(explorer_default)s, %(land_grid_state)s, %(land_grid_scope)s, %(status_dataset_detail)s,
    %(rationale)s)
on conflict do nothing
"""

# Guarded on residency exactly as the migration is, so the two writers are one writer: a rule
# row cannot exist before its conformance rule, and gate (b) in test_jurisdiction_parity.py is
# what refuses a registration whose rules never arrived.
_INSERT_RULE = """
insert into lineage.jurisdiction_rules
    (jurisdiction_code, effective_from, published_at, decision, rule_id, serving, note)
select %(jurisdiction_code)s, %(effective_from)s, %(published_at)s, %(decision)s,
       %(rule_id)s, %(serving)s, %(note)s
 where exists (select 1 from lineage.conformance_rules where rule_id = %(rule_id)s)
on conflict do nothing
"""


def registration_parameters(row: dict[str, object]) -> dict[str, object]:
    prefix = str(row["identity_prefix"])
    return {
        **row,
        "effective_from": REGISTERED_ON,
        "published_at": REGISTERED_ON,
        "evidence_tag": EVIDENCE_TAG,
        "evidence_commit": EVIDENCE_COMMIT,
        "identity_scheme": "api10",
        "identity_is_unique": True,
        "identity_pattern": identity_pattern(prefix),
        "source_ids": list(row["source_ids"]),  # type: ignore[arg-type]
    }


def rule_parameters(row: dict[str, object]) -> dict[str, object]:
    return {
        "effective_from": REGISTERED_ON,
        "published_at": REGISTERED_ON,
        "serving": True,
        "note": None,
        **row,
    }


def seed_jurisdictions(connection: psycopg.Connection) -> int:
    """Idempotent by contract: seed_all runs on every deploy. Returns the registry total."""
    with connection.cursor() as cursor:
        cursor.executemany(_INSERT_CODE, JURISDICTION_CODES)
        cursor.executemany(
            _INSERT_JURISDICTION, [registration_parameters(row) for row in JURISDICTIONS]
        )
        cursor.executemany(_INSERT_RULE, [rule_parameters(row) for row in JURISDICTION_RULES])
        # The read-time status resolver is derived from the rows above, and a database restored
        # from a dump lands them without an append for the trigger to see. Every deploy runs
        # this, between migrate and the API restart.
        cursor.execute("select lineage.refresh_status_resolution()")
        cursor.execute("select count(*) from lineage.jurisdictions")
        return int(cursor.fetchone()[0])
