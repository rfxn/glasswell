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

from glasswell.seed.conformance_basin_context import BASIN_CONTEXT
from glasswell.seed.conformance_co import (
    CLASSED_COUNT,
    CO_STATUS_MAP,
    DOCUMENTED_COUNT,
    PLANNED_SHARE,
)
from glasswell.seed.conformance_status_history import HISTORY_RULE_ID, STATUS_HISTORY

# Valid time and knowledge time of the founding registrations. The integrator repoints this
# beside the evidence pair, per the REPOINT CHECKLIST at the head of the migration.
REGISTERED_ON = date(2026, 9, 2)
EVIDENCE_TAG = "v0.76"
EVIDENCE_COMMIT = "6f2e9e6e97952000985568e6aa04d479ec84fe83"

# Knowledge time of the restatements that carry the presentation columns. Strictly later than
# every founding published_at, and not REGISTERED_ON + 1 day: two standing gates plant a rival
# registration on that instant and the partial unique indexes would refuse them.
RESTATED_ON = date(2026, 9, 4)
RESTATED_EVIDENCE_TAG = "v0.78"
# Spelled out rather than computed: release.py scans this file for the quoted placeholder, and
# an expression that evaluates to it is invisible to that scan, so the tag alone would have
# blocked and a half-repoint would have cleared the gate with a placeholder bound for an
# append-only table.
RESTATED_EVIDENCE_COMMIT = "5b37bf0363095b3e0cda2d6c3fb5d57e235de28f"

# Colorado's own clock, named separately so the integrator can repoint it on its own train.
# It is registered after the presentation columns exist, so it is founded whole: there is no
# instant at which it was published without them and nothing to restate. It is NOT later than
# the restatement, and cannot be: canonical.status_resolution resolves its arm through
# jurisdictions_as_of(current_date, current_date), so a registration dated ahead of the deploy
# host's today resolves nowhere and Colorado's statuses read as unmapped on the map.
CO_REGISTERED_ON = REGISTERED_ON
CO_EVIDENCE_TAG = "v0.78"
# Spelled out, not computed: the release gate greps for the literal, and a placeholder it
# cannot see is a placeholder that ships.
CO_EVIDENCE_COMMIT = "5b37bf0363095b3e0cda2d6c3fb5d57e235de28f"

# The web Wells rows as registration data. Seven facts that lived as object literals in
# `web/src/map/registry.ts`, so a fifth jurisdiction is a row rather than a hand edit.
PRESENTATION_COLUMNS = (
    "wells_layer_id",
    "wells_style_layer_ids",
    "wells_draw_order",
    "wells_default_on",
    "wells_snapshot_key",
    "wells_subtitle_template",
    "legend_note",
)

# The conformance rules this train publishes. The migration writes their publication evidence
# so the seeders can insert them: 049's trigger refuses a rule with no published vintage.
TRACK_RULE_IDS = (
    "cr_mt_neighbors_scope_1",
    "cr_mt_paths_length_scope_2",
    "cr_nd_basin_scope_1",
    "cr_nd_length_source_1",
    "cr_nd_neighbors_scope_1",
    "cr_tx_basin_scope_1",
    "cr_tx_length_source_1",
)

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
    {"jurisdiction_code": "CO", "level": "state"},
)

FOUNDING_JURISDICTIONS: tuple[dict[str, object], ...] = (
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
        # The irregular one: the founding layer id predates the per-jurisdiction spelling and
        # is frozen by every saved permalink, so the registry carries the irregularity.
        "wells_layer_id": "wells",
        "wells_style_layer_ids": ("wells", "wells-struck"),
        "wells_draw_order": 40,
        "wells_default_on": True,
        "wells_snapshot_key": "nd_wells_refresh",
        "wells_subtitle_template": (
            "ND DMR GIS surface locations · {count} points · culled by status below zoom 9"
        ),
        "legend_note": None,
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
        "wells_layer_id": "tx-wells",
        "wells_style_layer_ids": ("tx-wells", "tx-wells-struck"),
        "wells_draw_order": 42,
        "wells_default_on": True,
        "wells_snapshot_key": None,
        "wells_subtitle_template": (
            "TX RRC GIS surface locations, 55 Permian-district counties · {count} points"
        ),
        "legend_note": None,
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
        "wells_layer_id": "nm-wells",
        "wells_style_layer_ids": ("nm-wells", "nm-wells-struck"),
        "wells_draw_order": 43,
        "wells_default_on": True,
        "wells_snapshot_key": None,
        "wells_subtitle_template": (
            "NM OCD well-header surface locations · {count} points, ten of the fourteen OCD"
            " status codes mapped and four documented without an equivalent"
            " (cr_nm_wellhistory_status_vocab_2)"
        ),
        "legend_note": None,
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
        "wells_layer_id": "mt-wells",
        "wells_style_layer_ids": ("mt-wells", "mt-wells-struck"),
        "wells_draw_order": 44,
        "wells_default_on": True,
        "wells_snapshot_key": None,
        "wells_subtitle_template": (
            "MBOGC surface locations · {count} points, 13 of the 19 filed status values mapped"
            " and the other 6 quarantined rather than defaulted (cr_mt_gis_status_vocab_1) · no"
            " basin tag: Bakken is 4.6% of Montana (cr_mt_basin_scope_1) · completion year,"
            " never a spud"
        ),
        "legend_note": None,
        "rationale": (
            "Served from the MBOGC GIS layers and the two historical production files. The PRU"
            " file reports at lease grain, so its inventory rule is registered and not serving;"
            " the well paths are cartographic centrelines, which is why length has its own"
            " scope decision."
        ),
    },
)

# Small integers as words, the way every other subtitle spells them. The map exists so the
# two counts below can be computed from the seeded codebook rather than typed: they are served
# UI text, and an earlier hand-written pair of them was wrong.
_SPELLED = {
    2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine",
    10: "ten", 11: "eleven", 12: "twelve", 13: "thirteen", 14: "fourteen", 15: "fifteen",
    16: "sixteen", 17: "seventeen", 18: "eighteen", 19: "nineteen", 20: "twenty",
}

CO_SUBTITLE = (
    f"ECMC well headers \u00b7 {{count}} points, {_SPELLED[CLASSED_COUNT]} of"
    f" {_SPELLED[len(CO_STATUS_MAP)]} published status codes classed and"
    f" {_SPELLED[DOCUMENTED_COUNT]} documented without an equivalent"
    f" (cr_co_wells_status_vocab_1) \u00b7 {PLANNED_SHARE} of points are permit locations, not"
    " surveyed (cr_co_wells_location_qualifier_1) \u00b7 surface points only"
)

COLORADO: dict[str, object] = {
    "jurisdiction_code": "CO",
    "name": "Colorado",
    "regulator_name": "Colorado Energy and Carbon Management Commission",
    "regulator_url": "https://ecmc.state.co.us",
    "identity_prefix": "05",
    "source_ids": (
        "co_ecmc_wells_shp",
        "co_ecmc_directional_bh",
        "co_ecmc_directional_lines",
        "co_ecmc_monthly_prod",
        "co_ecmc_prod_reports",
    ),
    "liquids_basis": "oil+condensate",
    "wells_tile_layer_id": "co_wells",
    # The plugged grey, on a measured reason rather than by imitation: plugged is 44.75% of
    # Colorado against active's 28.62%, so a green dot would promise a canvas that never comes.
    "map_colour": "#7C8B96",
    "neighbors_available": False,
    "explorer_default": False,
    "land_grid_state": False,
    "land_grid_scope": False,
    "status_dataset_detail": SHARED_STATUS_DETAIL,
    "wells_layer_id": "co-wells",
    "wells_style_layer_ids": ("co-wells", "co-wells-struck"),
    # After Montana's 44. A real per-row integer, and above the founding row's 40, which the
    # client reads as the default wells source.
    "wells_draw_order": 45,
    "wells_default_on": True,
    "wells_snapshot_key": None,
    "wells_subtitle_template": CO_SUBTITLE,
    # The measured share is in the rule's own spec with the date it was taken, and the note
    # cites it: ECMC refreshes daily, so a count baked into a served string is the defect the
    # presentation columns exist to remove.
    "legend_note": (
        "Colorado's AL code is a vacated permit, not an abandoned well: those points have no"
        " wellbore and are drawn as expired permits (cr_co_wells_status_vocab_1)."
    ),
    "rationale": (
        "Served from the ECMC GIS shapefiles and the rolling production CSV. The status class"
        " is resolved at read time rather than written by the promotion, because the header"
        " refreshes daily against an append-only spine; ECMC files one liquid stream with no"
        " condensate column, so the liquids basis is oil plus condensate by the shape of the"
        " filing rather than by a rollup; and inventory is a registered refusal rather than an"
        " omission, because no PLSS grid, no spacing-unit source and no support score exist for"
        " Colorado and Protocol 4D admits no slot without them."
    ),
}

JURISDICTIONS: tuple[dict[str, object], ...] = (*FOUNDING_JURISDICTIONS, COLORADO)

# The founding rows, for the migration mirror and the parity gate. Named for what they restate
# rather than for what they hold, which reads backwards on first grep: they are `JURISDICTIONS`
# as v0.76 published them, before the seven presentation columns. Derived, never restated --
# a second copy of four rationales is the drift this registry exists to remove.
JURISDICTION_RESTATEMENTS: tuple[dict[str, object], ...] = tuple(
    {key: value for key, value in row.items() if key not in PRESENTATION_COLUMNS}
    for row in FOUNDING_JURISDICTIONS
)

JURISDICTION_RULES_AS_FOUNDED: tuple[dict[str, object], ...] = (
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


# Colorado's decisions, at Colorado's own instant. Thirteen rows: every §3 rule that decides
# something the serving path resolves through the registry. The two parse rules that ride with
# the production grain are conformance rows without being registry decisions, and the six
# cadence rules are registered in the scheduler's tables rather than here. So is
# cr_co_wells_well_type_1: the registry has no well-type decision, here or for any other
# jurisdiction -- ND's cr_nd_well_type_disposal_1 and NM's cr_nm_wellhistory_well_type_1 are
# published conformance rules under no decision either, and a well_type_vocabulary key is the
# v0.80 registry-vocabulary question rather than one this train answers.
COLORADO_DECISIONS: tuple[dict[str, object], ...] = tuple(
    {
        "jurisdiction_code": "CO",
        "decision": decision,
        "rule_id": rule_id,
        "effective_from": CO_REGISTERED_ON,
        "published_at": CO_REGISTERED_ON,
    }
    for decision, rule_id in (
        ("status_vocabulary", "cr_co_wells_status_vocab_1"),
        ("identity", "cr_co_wells_api10_1"),
        ("deduplication", "cr_co_wells_dedup_1"),
        ("source_selection", "cr_co_wells_source_selection_1"),
        ("crs", "cr_co_wells_datum_1"),
        ("geometry_provenance", "cr_co_wells_geometry_provenance_1"),
        ("location_qualifier", "cr_co_wells_location_qualifier_1"),
        ("geometry_scope", "cr_co_wells_geometry_scope_1"),
        ("inventory_jurisdiction", "cr_co_inventory_not_served_1"),
        ("liquids", "cr_co_production_liquids_1"),
        ("entity_key", "cr_co_production_entity_key_1"),
        ("production_grain", "cr_co_production_grain_1"),
        ("cumulatives_scope", "cr_co_production_grain_1"),
    )
)

# The resolved set. Montana's length_scope repoints to the appended successor, whose spec drops
# the sentence describing the North Dakota default this track removes; four basin_scope rows say
# which basin governs a jurisdiction's compute CRS; two length_source rows say which source
# computes a lateral, a fact `length_scope` cannot carry because the serving path reads that
# decision's existence as "withheld"; two neighbors_scope rows say the neighbour mart's measured
# domain reaches this jurisdiction.
JURISDICTION_RULES: tuple[dict[str, object], ...] = (
    *(
        {**row, "rule_id": "cr_mt_paths_length_scope_2"}
        if row["decision"] == "length_scope"
        else row
        for row in JURISDICTION_RULES_AS_FOUNDED
    ),
    {"jurisdiction_code": "ND", "decision": "basin_scope", "rule_id": "cr_nd_basin_scope_1"},
    {"jurisdiction_code": "TX", "decision": "basin_scope", "rule_id": "cr_tx_basin_scope_1"},
    {"jurisdiction_code": "NM", "decision": "basin_scope",
     "rule_id": "cr_nm_wellhistory_basin_scope_1"},
    {"jurisdiction_code": "MT", "decision": "basin_scope", "rule_id": "cr_mt_basin_scope_1"},
    {"jurisdiction_code": "ND", "decision": "length_source",
     "rule_id": "cr_nd_length_source_1"},
    {"jurisdiction_code": "TX", "decision": "length_source",
     "rule_id": "cr_tx_length_source_1"},
    # The two jurisdictions whose header effective_from is the regulator's own valid time, and
    # the whole of what emits links.history. Registered at each one's own clock: Colorado's
    # registration was founded at its own instant and jurisdiction_rules carries a composite
    # foreign key onto it, so a row at the restatement's clock would point at no registration.
    # The polygon answer, one rule per jurisdiction. A new decision rather than a repoint of
    # basin_scope: that rule decides whether the ingest writes canonical.wells.basin at all and
    # is still true, and these decide what the published boundaries say about the same well.
    {"jurisdiction_code": "ND", "decision": BASIN_CONTEXT, "rule_id": "cr_nd_basin_context_1"},
    {"jurisdiction_code": "TX", "decision": BASIN_CONTEXT, "rule_id": "cr_tx_basin_context_1"},
    {"jurisdiction_code": "MT", "decision": BASIN_CONTEXT, "rule_id": "cr_mt_basin_context_1"},
    {"jurisdiction_code": "NM", "decision": BASIN_CONTEXT, "rule_id": "cr_nm_basin_context_1"},
    {"jurisdiction_code": "CO", "decision": BASIN_CONTEXT, "rule_id": "cr_co_basin_context_1",
     "effective_from": CO_REGISTERED_ON, "published_at": CO_REGISTERED_ON},
    {"jurisdiction_code": "NM", "decision": STATUS_HISTORY, "rule_id": HISTORY_RULE_ID},
    {"jurisdiction_code": "CO", "decision": STATUS_HISTORY, "rule_id": HISTORY_RULE_ID,
     "effective_from": CO_REGISTERED_ON, "published_at": CO_REGISTERED_ON},
    {"jurisdiction_code": "ND", "decision": "neighbors_scope",
     "rule_id": "cr_nd_neighbors_scope_1"},
    {"jurisdiction_code": "MT", "decision": "neighbors_scope",
     "rule_id": "cr_mt_neighbors_scope_1"},
    # Which jurisdictions the per-well cumulative mart covers, as rows rather than as a tuple
    # in the mart. The rule each names is the one that decides whether the jurisdiction writes
    # a well-grain row at all: without one the mart would enter every well, match no month and
    # write never_reported over a jurisdiction whose production is sitting in canonical.
    {"jurisdiction_code": "ND", "decision": "cumulatives_scope",
     "rule_id": "cr_nd_pool_rollup_1"},
    *COLORADO_DECISIONS,
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
    status_dataset_detail, rationale, wells_layer_id, wells_style_layer_ids, wells_draw_order,
    wells_default_on, wells_snapshot_key, wells_subtitle_template, legend_note)
values (
    %(jurisdiction_code)s, %(effective_from)s, %(published_at)s, %(evidence_tag)s,
    %(evidence_commit)s, %(name)s, %(regulator_name)s, %(regulator_url)s, %(identity_scheme)s,
    %(identity_is_unique)s, %(identity_prefix)s, %(identity_pattern)s, %(source_ids)s,
    %(liquids_basis)s, %(wells_tile_layer_id)s, %(map_colour)s, %(neighbors_available)s,
    %(explorer_default)s, %(land_grid_state)s, %(land_grid_scope)s, %(status_dataset_detail)s,
    %(rationale)s, %(wells_layer_id)s, %(wells_style_layer_ids)s, %(wells_draw_order)s,
    %(wells_default_on)s, %(wells_snapshot_key)s, %(wells_subtitle_template)s,
    %(legend_note)s)
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


def registration_parameters(
    row: dict[str, object],
    *,
    effective_from: date = REGISTERED_ON,
    published_at: date = REGISTERED_ON,
    evidence_tag: str = EVIDENCE_TAG,
    evidence_commit: str = EVIDENCE_COMMIT,
) -> dict[str, object]:
    """The clock and its evidence arrive as arguments, never as a literal a row could shadow."""
    prefix = str(row["identity_prefix"])
    presentation: dict[str, object] = {column: row.get(column) for column in PRESENTATION_COLUMNS}
    style_layers = presentation["wells_style_layer_ids"]
    if isinstance(style_layers, tuple):
        presentation["wells_style_layer_ids"] = list(style_layers)
    return {
        **row,
        **presentation,
        "effective_from": effective_from,
        "published_at": published_at,
        "evidence_tag": evidence_tag,
        "evidence_commit": evidence_commit,
        "identity_scheme": "api10",
        "identity_is_unique": True,
        "identity_pattern": identity_pattern(prefix),
        "source_ids": list(row["source_ids"]),  # type: ignore[arg-type]
    }


def colorado_parameters() -> dict[str, object]:
    """The fifth registration, founded whole at its own instant with its own evidence pair."""
    return registration_parameters(
        COLORADO,
        effective_from=CO_REGISTERED_ON,
        published_at=CO_REGISTERED_ON,
        evidence_tag=CO_EVIDENCE_TAG,
        evidence_commit=CO_EVIDENCE_COMMIT,
    )


def restatement_parameters(row: dict[str, object]) -> dict[str, object]:
    """A resolved registration stamped with this train's clock and its own evidence pair."""
    return registration_parameters(
        row,
        published_at=RESTATED_ON,
        evidence_tag=RESTATED_EVIDENCE_TAG,
        evidence_commit=RESTATED_EVIDENCE_COMMIT,
    )


def rule_parameters(
    row: dict[str, object], *, published_at: date = REGISTERED_ON
) -> dict[str, object]:
    """A row may carry its own clock: a registration founded later declares its rules there."""
    return {
        "effective_from": REGISTERED_ON,
        "serving": True,
        "note": None,
        **row,
        "published_at": row.get("published_at", published_at),
    }


def seed_jurisdictions(connection: psycopg.Connection) -> int:
    """Idempotent by contract: seed_all runs on every deploy. Returns the registry total.

    Two clocks, two rule sets: the founding instant keeps the decisions v0.76 knew about, and
    the restatement carries those plus the ones this train registers. Writing the new rows at
    the founding instant would be an edit to what was published, spelled as an append.
    """
    with connection.cursor() as cursor:
        cursor.executemany(_INSERT_CODE, JURISDICTION_CODES)
        cursor.executemany(
            _INSERT_JURISDICTION,
            [registration_parameters(row) for row in JURISDICTION_RESTATEMENTS]
            + [restatement_parameters(row) for row in FOUNDING_JURISDICTIONS]
            + [colorado_parameters()],
        )
        cursor.executemany(
            _INSERT_RULE,
            [rule_parameters(row) for row in JURISDICTION_RULES_AS_FOUNDED]
            + [rule_parameters(row, published_at=RESTATED_ON) for row in JURISDICTION_RULES],
        )
        # The read-time status resolver is derived from the rows above, and a database restored
        # from a dump lands them without an append for the trigger to see. Every deploy runs
        # this, between migrate and the API restart.
        cursor.execute("select lineage.refresh_status_resolution()")
        cursor.execute("select count(*) from lineage.jurisdictions")
        return int(cursor.fetchone()[0])
