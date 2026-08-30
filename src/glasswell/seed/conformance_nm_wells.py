"""New Mexico well-header conformance rules: the mapping decisions the spine needs (R8).

The 79 NM rules already resident cover fetch, parse and the production spine. None of them
decides anything about a *well header*: there is no identity rule for `wellhistory`, no header
field mapping, no datum rule, no geometry provenance and no statement of what New Mexico's pool
grain means for a served figure. Every one of those is a cross-source mapping decision, so it is
a row here before an executor reads it, not a literal in `ingest/nm_wells.py`.

Two measurements underlie most of these rows, taken by streaming the sealed 2026-08-20
`wellhistory` artifact end to end — first by the planner, then independently again while these
rules were written, with every figure reproduced.
"""

from __future__ import annotations

from datetime import date

import psycopg
from psycopg.types.json import Jsonb

EFFECTIVE_FROM = date(2026, 8, 30)

OCD_FTP_PAGE_URL = "https://wwwapps.emnrd.nm.gov/OCD/OCDPermitting/Data/Download.aspx"
OCD_FTP_DESCRIPTIONS_URL = (
    "https://wwwapps.emnrd.nm.gov/OCD/OCDPermitting/Data/DataDownloadDescriptions.aspx"
)

# Both scans agree, record for record, over all 321,510 records of the 2026-08-20 artifact.
RECORDS_MEASURED = 321510
USABLE_PAIRS = 318720
COORDINATE_ABSENT = 1893
COORDINATE_SENTINEL = 897
DISTINCT_API10S = 142000
API10S_WITH_A_POINT = 141778

# status and well_typ_cde over the same scan; the key '&#x20;' is the source's own escaped
# single space, which is CHAR padding rather than a code.
STATUS_DOMAIN = {
    "A": 206195, "P": 50211, "N": 36615, "C": 17400, "H": 4762, "T": 2512, "Q": 1652,
    "E": 733, "S": 506, "J": 486, "X": 331, "Z": 62, "D": 34, "&#x20;": 6, "I": 5,
}
WELL_TYPE_DOMAIN = {
    "O": 176989, "G": 116934, "I": 20404, "S": 4383, "C": 1774, "M": 705, "W": 320,
    "&#x20;": 1,
}
DIRECTIONAL_DOMAIN = {
    "V": 136164, "absent": 133507, "H": 43409, "&#x20;": 5163, "D": 3265, "M": 2,
}

NM_WELLS_RULES: tuple[dict[str, object], ...] = (
    {
        "rule_id": "cr_nm_wellhistory_api10_1",
        "source_id": "nm_ocd_wellhistory",
        "stage": "conform",
        "rule_kind": "key_composite",
        "applies_to_fields": ["api_st_cde", "api_cnty_cde", "api_well_idn"],
        "spec": {
            "source_cols": ["api_st_cde", "api_cnty_cde", "api_well_idn"],
            "pad": {"api_st_cde": 2, "api_cnty_cde": 3, "api_well_idn": 5},
            "min_width": {"api_st_cde": 2},
            "charset": {
                "api_st_cde": "digits",
                "api_cnty_cde": "digits",
                "api_well_idn": "digits",
            },
            "pad_char": "0",
            "pad_side": "left",
            "separator": "",
            "target_col": "api10",
            "state_code": "30",
            "on_missing": "quarantine",
            "reason_code": "key_incomplete",
            "mirrors_rule_id": "cr_nm_wcproduction_api10_1",
            "measured": {
                "records": RECORDS_MEASURED,
                "distinct_api10": DISTINCT_API10S,
                "over_wide_api_well_idn": 0,
            },
        },
        "rule": (
            "The header API-10 is state code 30, the county code padded to three and the well"
            " number padded to five, concatenated as SSCCCUUUUU — the same composition the"
            " production spine uses, per segment."
        ),
        "rationale": (
            "The header table must key identically to the production spine or the two halves of"
            " New Mexico never join, so this row mirrors cr_nm_wcproduction_api10_1 rather than"
            " restating it in a second idiom. Padding is per segment for the reason that rule"
            " records over 48.1M rows: concatenating first and padding the result gives"
            " '30'+'1'+'5005' -> 0030105005, not 3000105005, which is a different well."
            " The one difference from the spine is measured and worth the row: across all"
            " 321,510 header records api_well_idn never exceeds five characters, so this path"
            " raises no key_incomplete, where wcproduction had exactly one over-wide record it"
            " had to refuse. 30 is New Mexico's API state code and not its FIPS code (35), which"
            " is why the prefix is a rule rather than a slice of a field that looks like it"
            " already carries one."
        ),
        "evidence_url": OCD_FTP_PAGE_URL,
        "code_ref": "src/glasswell/ingest/nm_wells.py",
    },
    {
        "rule_id": "cr_nm_wellhistory_effective_1",
        "source_id": "nm_ocd_wellhistory",
        "stage": "conform",
        "rule_kind": "parse_directive",
        "applies_to_fields": ["eff_dte", "rec_termn_dte"],
        "spec": {
            "effective_from_field": "eff_dte",
            "effective_to_field": "rec_termn_dte",
            "open_interval_sentinel": "9999-12-31",
            "measured_eff_dte_range": ["1900-01-01", "2026-08-19"],
            "backfill_rows_kept": True,
        },
        "rule": (
            "eff_dte is the header row's valid-time start and rec_termn_dte its end;"
            " 9999-12-31 is the open sentinel and becomes a null effective_to."
        ),
        "rationale": (
            "The staged range runs 1900-01-01 to 2026-08-19. The 1900-01-01 rows are the"
            " regulator's own pre-ONGARD backfill, and they are kept: an effective-dated table is"
            " exactly where a regulator's backfill belongs, and dropping it would make the well's"
            " history start on the day the state's database did. The 9999-12-31 sentinel is"
            " translated rather than stored, because a served effective_to of the year 9999 is a"
            " number a reader has to know a convention to interpret, and null is the convention"
            " canonical.wells already uses."
        ),
        "evidence_url": OCD_FTP_DESCRIPTIONS_URL,
        "code_ref": "src/glasswell/ingest/nm_wells.py",
    },
    {
        "rule_id": "cr_nm_wellhistory_status_vocab_1",
        "source_id": "nm_ocd_wellhistory",
        "stage": "conform",
        "rule_kind": "parse_directive",
        "applies_to_fields": ["all"],
        "spec": {
            "declares_fields": ["status"],
            "asserts_header": False,
            "promoted_to": "status_reported",
            "status_canonical": None,
            "mapping_table": None,
            "measured_domain": STATUS_DOMAIN,
            "measured_rows": RECORDS_MEASURED,
            "blank_is_data": True,
            "follows_rule_id": "cr_nm_wchistory_status_domain_1",
        },
        "rule": (
            "wellhistory.status has fifteen values and they are promoted verbatim as"
            " status_reported. status_canonical stays null because no codebook maps them."
        ),
        "rationale": (
            "Measured over all 321,510 header records: A 206,195, P 50,211, N 36,615, C 17,400,"
            " H 4,762, T 2,512, Q 1,652, E 733, S 506, J 486, X 331, Z 62, D 34, a single space"
            " 6 and I 5. The counts sum to the record count exactly, so the domain is closed"
            " rather than sampled. Measuring a domain does not produce a mapping: the OCD"
            " publishes no codebook for these letters, and guessing that A is active would put"
            " an unlabelled estimate in the status column — the R8 violation this registry"
            " exists to prevent. cr_nm_wchistory_status_domain_1 already ruled exactly this way"
            " for the completion table's own status code, and lineage.nm_status_map stays empty"
            " for the same reason. So an NM well carries its letter in status_reported and null"
            " in status_canonical: an absent mapping, not a mapping to null. That is why the"
            " served status summary counts every New Mexico well as unmapped, and why this row is"
            " the rule that figure cites — an unmapped count with a rule behind it is a"
            " measurement; without one it is a naked number."
        ),
        "evidence_url": OCD_FTP_DESCRIPTIONS_URL,
        "code_ref": "src/glasswell/ingest/nm_wells.py",
    },
    {
        "rule_id": "cr_nm_wellhistory_well_type_1",
        "source_id": "nm_ocd_wellhistory",
        "stage": "conform",
        "rule_kind": "parse_directive",
        "applies_to_fields": ["all"],
        "spec": {
            "declares_fields": ["well_typ_cde"],
            "asserts_header": False,
            "promoted_to": "well_type_reported",
            "canonical_mapping": None,
            "measured_domain": WELL_TYPE_DOMAIN,
            "measured_rows": RECORDS_MEASURED,
        },
        "rule": (
            "well_typ_cde has eight values and is promoted verbatim as well_type_reported;"
            " no canonical well-type class is asserted from it."
        ),
        "rationale": (
            "Measured over all 321,510 records: O 176,989, G 116,934, I 20,404, S 4,383, C"
            " 1,774, M 705, W 320 and a single space once. The column is named for what it is —"
            " the type the operator reported — and canonical.wells stores it under that name, so"
            " promoting it verbatim asserts nothing. Reading I as injection and S as salt water"
            " disposal is the obvious guess and is exactly the guess this registry refuses"
            " without a codebook: Texas needed a twenty-four-row mapping table with a published"
            " manual behind it before it could class an injector, and New Mexico has no such"
            " manual for this column."
        ),
        "evidence_url": OCD_FTP_DESCRIPTIONS_URL,
        "code_ref": "src/glasswell/ingest/nm_wells.py",
    },
    {
        "rule_id": "cr_nm_wellhistory_datum_1",
        "source_id": "nm_ocd_wellhistory",
        "stage": "conform",
        "rule_kind": "datum_transform",
        "applies_to_fields": ["latitude", "longitude", "datum"],
        "spec": {
            "source_epsg": 4269,
            "target_epsg": 4326,
            "detect": {
                "column": "datum",
                "value": "NAD83",
                "lat_col": "latitude",
                "lon_col": "longitude",
            },
            "measured_datum_domain": {"NAD83": RECORDS_MEASURED},
            "on_unexpected_datum": "quarantine",
            "reason_code": "unknown_vocab",
        },
        "rule": "Transform the NAD83 header coordinates to EPSG:4326 before they reach storage.",
        "rationale": (
            "datum is the literal NAD83 on 321,510 of 321,510 records — one value, no"
            " mixed-datum case, so the transform is unconditional rather than per row. Storage"
            " is always 4326 and the transform is recorded as a derivation even though the shift"
            " is sub-metre: no coordinate reaches storage untransformed and unrecorded, which is"
            " the same rule cr_nd_datum_1, cr_blm_plss_datum_1 and cr_nm_c115b_datum_1 state for"
            " their sources. A record arriving under any other datum is quarantined rather than"
            " assumed, because the measurement that makes this rule unconditional is a"
            " measurement of one artifact and not a promise about the next one."
        ),
        "evidence_url": OCD_FTP_DESCRIPTIONS_URL,
        "code_ref": "src/glasswell/ingest/nm_wells.py",
    },
    {
        "rule_id": "cr_nm_wellhistory_coordinate_1",
        "source_id": "nm_ocd_wellhistory",
        "stage": "validate",
        "rule_kind": "parse_directive",
        "applies_to_fields": ["all"],
        "spec": {
            "declares_fields": ["latitude", "longitude"],
            "asserts_header": False,
            "unit": "pair",
            "number_format": "scientific",
            "parse": "float",
            "precedence": ["nil", "zero"],
            "outcomes": {
                "promote": "both ordinates non-nil and non-zero",
                "coordinate_absent": "either ordinate nil, checked first",
                "coordinate_sentinel": "neither nil and either ordinate zero",
            },
            "header_is_promoted_regardless": True,
            "measured": {
                "records": RECORDS_MEASURED,
                "usable_pair": USABLE_PAIRS,
                "coordinate_absent": COORDINATE_ABSENT,
                "coordinate_sentinel": COORDINATE_SENTINEL,
                "both_zero": 893,
                "longitude_zero_only": 4,
                "distinct_api10": DISTINCT_API10S,
                "distinct_api10_with_a_point": API10S_WITH_A_POINT,
                "scientific_notation_ordinates": 639237,
                "plain_decimal_ordinates": 0,
            },
        },
        "rule": (
            "A header promotes a surface point only when latitude and longitude are both"
            " non-nil and both non-zero. Either ordinate nil quarantines the geometry as"
            " coordinate_absent; failing that, either ordinate zero quarantines it as"
            " coordinate_sentinel. Nil is checked first. Neither refusal suppresses the well"
            " header."
        ),
        "rationale": (
            "This is a rule about the pair, not about either ordinate, because ST_MakePoint"
            " consumes both and raises on neither. 318,720 of 321,510 records carry a usable"
            " pair, 1,893 carry a nil ordinate and 897 a zero one; the three populations were"
            " counted separately and sum to the record count, so the reconciliation closes on"
            " measurement rather than on subtraction. 141,778 of 142,000 distinct API-10s get at"
            " least one point."
            " The non-obvious part is the longitude: a zero longitude is undetectable by any"
            " range check, because 0.0 is a valid longitude everywhere on Earth. It is a"
            " sentinel here only because New Mexico is not at Greenwich. Four records carry a"
            " good New Mexico latitude and a longitude of exactly zero, and a latitude-only"
            " check would have given those four wells a perfectly valid point in the Gulf of"
            " Guinea, about 9,000 km away, in an append-only table, on a published tile layer."
            " Precedence is nil before zero because three records are mixed — nil on one"
            " ordinate and valued on the other — so two independent per-ordinate rules cannot"
            " express the policy and the order has to be stated rather than left to evaluation."
            " Both ordinates arrive in scientific notation on every record that has one:"
            " 639,237 of 639,237 values, zero plain decimals, so a parser that string-slices or"
            " assumes a decimal point fails on the whole file rather than on a subset."
        ),
        "evidence_url": OCD_FTP_PAGE_URL,
        "code_ref": "src/glasswell/ingest/nm_wells.py",
    },
    {
        "rule_id": "cr_nm_wellhistory_geometry_provenance_1",
        "source_id": "nm_ocd_wellhistory",
        "stage": "conform",
        "rule_kind": "parse_directive",
        "applies_to_fields": ["all"],
        "spec": {
            "declares_fields": ["latitude", "longitude"],
            "asserts_header": False,
            "canonical_column": "geometry_provenance",
            "served_from": "canonical.well_spatial.geom_type",
            "value": "surface",
            "verbatim": True,
            "mirrors_rule_id": "cr_nd_geometry_provenance_1",
        },
        "rule": (
            "A New Mexico well's geometry_provenance is its geom_type served verbatim, and the"
            " only geom_type this source produces is surface."
        ),
        "rationale": (
            "geometry_provenance is a served field, so it needs a rule to cite in New Mexico for"
            " the same reason it needed one in North Dakota: without it the API resolves every"
            " state's provenance to cr_nd_geometry_provenance_1 and a New Mexico figure carries"
            " a North Dakota handle. The value is not derived — it is the geom_type column, and"
            " saying so is the whole content of the rule, which is what makes it checkable."
        ),
        "evidence_url": OCD_FTP_DESCRIPTIONS_URL,
        "code_ref": "src/glasswell/api/routers/wells.py",
    },
    {
        "rule_id": "cr_nm_wellhistory_geometry_scope_1",
        "source_id": "nm_ocd_wellhistory",
        "stage": "conform",
        "rule_kind": "parse_directive",
        "applies_to_fields": ["all"],
        "spec": {
            "declares_fields": ["directional_status"],
            "asserts_header": False,
            "geom_types_produced": ["surface"],
            "geom_types_absent": ["lateral", "bottomhole", "survey_trace"],
            "measured_directional_status": DIRECTIONAL_DOMAIN,
            "measured_rows": RECORDS_MEASURED,
            "corroborating_source": "nm_ocd_wells_gis (esriGeometryPoint, surface only)",
        },
        "rule": (
            "No in-scope New Mexico source ships a lateral or a bottomhole. New Mexico geometry"
            " is a surface point and nothing else, whatever a well's directional status says."
        ),
        "rationale": (
            "directional_status is measured over all 321,510 records as V 136,164, absent"
            " 133,507, H 43,409, a single space 5,163, D 3,265 and M 2 — so 43,409 horizontal"
            " and 3,265 directional wells are present in the header table and none of them"
            " carries a path. The producing footprint of those 46,674 wells is therefore not"
            " represented at all, and this row exists so that no consumer reads a horizontal"
            " well's presence as evidence of a lateral. The corroborating OCD public wells layer"
            " is esriGeometryPoint and describes itself as the surface drilling location, so"
            " both independent New Mexico sources agree. A New Mexico lateral is"
            " data-unreachable rather than unbuilt, and the two measurements are its evidence."
        ),
        "evidence_url": OCD_FTP_DESCRIPTIONS_URL,
        "code_ref": "src/glasswell/ingest/nm_wells.py",
    },
    {
        "rule_id": "cr_nm_wcproduction_pool_rollup_1",
        "source_id": "nm_ocd_wcproduction",
        "stage": "conform",
        "rule_kind": "parse_directive",
        "applies_to_fields": ["all"],
        "spec": {
            "declares_fields": ["entity_type", "reporting_level", "aggregation"],
            "asserts_header": False,
            "entity_type": "well_completion_pool",
            "reporting_level": "well_completion_pool",
            "aggregation": None,
            "well_level_rows_promoted": 0,
            "rolls_up_to_the_well": False,
            "well_series_endpoint": "/v1/wells/{api10}/production",
            "pool_series_endpoint": "/v1/wells/{api10}/production/pools",
            "contrasts_rule_id": "cr_nd_pool_rollup_1",
            "measured": {
                "promoted_rows": 17597960,
                "distinct_entity_key": 80623,
                "distinct_api10": 70024,
                "distinct_pools": 2596,
                "entity_type_well_rows": 0,
            },
        },
        "rule": (
            "New Mexico production is filed and promoted at the well-completion-pool grain and"
            " glasswell performs no rollup to the well. A New Mexico well's series is its pool"
            " series; the well-level series is absent, not zero."
        ),
        "rationale": (
            "North Dakota's cr_nd_pool_rollup_1 answers the same question the opposite way, and"
            " the contrast is the point: ND promotes one row per pool plus a well total"
            " disclosed as sum_over_pools, so an ND well card can show a well-level series. All"
            " 17,597,960 New Mexico rows are entity_type well_completion_pool with a null"
            " aggregation and there is not one entity_type = well row among them, measured"
            " directly. Summing them here would be a rollup this registry has not decided:"
            " New Mexico's 80,623 entities span 70,024 wells, so 10,599 wells filed in more than"
            " one pool, and adding those filings would need the days-produced treatment and the"
            " null-semantics treatment that cr_nd_pool_rollup_1 spells out and that nobody has"
            " measured for this source. The consequence is a served one and must be disclosed"
            " rather than rendered as an empty chart: an empty well-level series reads as"
            " nothing produced, which is the failure DIR-3 names, so the well production surface"
            " cites this row and points at the pool surface instead. The pool surface's own"
            " aggregation_rule link cites this row too, because what it has to say about a New"
            " Mexico pool series is that no aggregation produced it."
        ),
        "evidence_url": OCD_FTP_DESCRIPTIONS_URL,
        "code_ref": "src/glasswell/api/routers/production.py",
    },
    {
        "rule_id": "cr_nm_wellhistory_header_precedence_1",
        "source_id": "nm_ocd_wellhistory",
        "stage": "join",
        "rule_kind": "code_ref",
        "applies_to_fields": ["api10", "effective_from", "status_reported", "geom"],
        "spec": {
            "module_function": "glasswell.ingest.nm_wells:promote",
            "version": "1",
            "authority": {
                "identity": "nm_ocd_wellhistory",
                "effective_dating": "nm_ocd_wellhistory",
                "status_reported": "nm_ocd_wellhistory",
                "well_type_reported": "nm_ocd_wellhistory",
                "surface_point": "nm_ocd_wellhistory",
            },
            "second_source": None,
            "superseded_when": "the GIS parity is measured (cr_nm_wells_gis_parity_1)",
            "contract_note": (
                "one source, so every field resolves to it; a second source changes this to a"
                " per-field decision through a superseding row, never through an ordering in the"
                " promoter"
            ),
        },
        "rule": (
            "The FTP header table is the sole authority for every New Mexico header field,"
            " including the surface point, until a second source has been measured against it."
        ),
        "rationale": (
            "New Mexico will have two independent measurements of the same well population: the"
            " frozen 2026-08-20 FTP header archive and the daily-refreshed OCD public wells"
            " layer. Which one wins per field is a cross-source mapping decision, so it is a row"
            " rather than an ordering in a promoter. It is seeded with a single authority"
            " because that is the true state before the parity is measured, and it is superseded"
            " by _2 once it is — a changed decision is a new row, never an edit."
        ),
        "evidence_url": OCD_FTP_DESCRIPTIONS_URL,
        "code_ref": "src/glasswell/ingest/nm_wells.py",
    },
)

_INSERT_RULE = """
insert into lineage.conformance_rules
    (rule_id, rule_family, supersedes_rule_id, source_id, stage, applies_to_fields, rule_kind,
     spec, rule, rationale, evidence_url, code_ref, effective_from)
values (%(rule_id)s, %(rule_family)s, %(supersedes_rule_id)s, %(source_id)s, %(stage)s,
        %(applies_to_fields)s, %(rule_kind)s, %(spec)s, %(rule)s, %(rationale)s,
        %(evidence_url)s, %(code_ref)s, %(effective_from)s)
on conflict do nothing
"""


def _row(rule: dict[str, object]) -> dict[str, object]:
    rule_id = str(rule["rule_id"])
    return {
        **rule,
        "rule_family": rule_id.rsplit("_", 1)[0],
        "spec": Jsonb(rule["spec"]),
        "code_ref": rule.get("code_ref"),
        "evidence_url": rule.get("evidence_url"),
        "supersedes_rule_id": rule.get("supersedes_rule_id"),
        "effective_from": rule.get("effective_from", EFFECTIVE_FROM),
    }


def seed_conformance_nm_wells(connection: psycopg.Connection) -> int:
    """Rule ids are immutable: a change is a new row with supersedes_rule_id (SB-07 §6.2).

    The count is over this module's own ids rather than over a source-id prefix, so it does not
    move when a sibling seeder adds a row under the same prefix.
    """
    rule_ids = [str(rule["rule_id"]) for rule in NM_WELLS_RULES]
    with connection.cursor() as cursor:
        cursor.executemany(_INSERT_RULE, [_row(rule) for rule in NM_WELLS_RULES])
        cursor.execute(
            "select count(*) from lineage.conformance_rules where rule_id = any(%s)",
            (rule_ids,),
        )
        return int(cursor.fetchone()[0])
