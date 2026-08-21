"""The TX conformance registry and source rows (SB-07 §6.2, SB-01 §2.8/§2.9).

Every rule here was established against files opened during the TX slice, and every count in a
rationale was measured on them: the 2026-08-20 county well layers and the 2026-08-20
`OG_WELLBORE_EWA_Report.csv` (1,310,392 records).
"""

from __future__ import annotations

from datetime import date

import psycopg
from psycopg.types.json import Jsonb

GIS_LINK = "https://mft.rrc.texas.gov/link/d551fb20-442e-4b67-84fa-ac3f23ecabb4"
EWA_LINK = "https://mft.rrc.texas.gov/link/650649b7-e019-4d77-a8e0-d118d6455381"
EWA_MANUAL = (
    "https://www.rrc.texas.gov/media/di1mm5or/"
    "og_wellbore_ewadefinitionmanual2013-10-30_subscription.pdf"
)
GIS_FAQ = "https://www.rrc.texas.gov/about-us/faqs/general-faq/digital-map-information-gis-data/"
DOWNLOADS_PAGE = (
    "https://www.rrc.texas.gov/resource-center/research/data-sets-available-for-download/"
)

EFFECTIVE_FROM = date(2026, 8, 20)

TX_LICENSE_NOTE = (
    "Free public download, no registration and no click-wall. The RRC disclaimer disclaims"
    " warranties and states the data have no legal force or effect; no redistribution"
    " restriction was found."
)

# The 55 county files whose district-bearing identity rows are at least half in RRC districts
# 08, 8A and 7C - the Commission's own Permian districts. Measured, not asserted: see
# cr_tx_county_scope_1's rationale.
PERMIAN_COUNTY_CODES: tuple[str, ...] = (
    "003", "017", "033", "043", "079", "081", "095", "101", "103", "105", "107", "109", "115",
    "125", "135", "141", "153", "165", "169", "173", "189", "219", "227", "229", "235", "243",
    "263", "267", "269", "279", "301", "303", "305", "307", "317", "327", "329", "335", "345",
    "371", "377", "383", "389", "399", "413", "415", "431", "435", "443", "445", "451", "461",
    "475", "495", "501",
)

# `+grids=` takes an absolute path so the transform reads the manifested artifact rather than
# whatever the host's PROJ happens to carry. `{grid_path}` is substituted from the grid's own
# manifest; nothing else in the pipeline is built at runtime.
NAD27_PIPELINE = (
    "+proj=pipeline +step +proj=axisswap +order=2,1 +step +proj=unitconvert +xy_in=deg"
    " +xy_out=rad +step +proj=hgridshift +grids={grid_path} +step +proj=unitconvert +xy_in=rad"
    " +xy_out=deg +step +proj=axisswap +order=2,1"
)

TX_SOURCES: tuple[dict[str, object], ...] = (
    {
        "source_id": "tx_gis_wells_county",
        "name": "TX RRC GIS well layers by county (well###.zip)",
        "jurisdiction": "TX",
        "license_note": TX_LICENSE_NOTE,
        "redistributable": False,
    },
    {
        "source_id": "tx_wellbore_ewa_csv",
        "name": "TX RRC Wellbore Query export (OG_WELLBORE_EWA_Report.csv)",
        "jurisdiction": "TX",
        "license_note": TX_LICENSE_NOTE,
        "redistributable": False,
    },
    {
        "source_id": "proj_grid_nad27",
        "name": "NOAA NADCON grid used by the NAD27 transform (us_noaa_conus.tif)",
        "jurisdiction": "US",
        "license_note": "Public domain NOAA grid, redistributed by the PROJ CDN.",
        "redistributable": True,
    },
)

TX_RULES: tuple[dict[str, object], ...] = (
    {
        "rule_id": "cr_tx_api10_build_1",
        "source_id": "tx_gis_wells_county",
        "stage": "join",
        "rule_kind": "key_composite",
        "applies_to_fields": ["api"],
        "spec": {
            "source_cols": ["state_code", "api"],
            "target_col": "api10",
            "separator": "",
            "pad": {"api": 8},
            "on_missing": "quarantine",
            "reason_code": "key_incomplete",
            "state_code": "42",
        },
        "rule": "API-10 is '42' followed by the RRC's eight-digit county-plus-well number.",
        "rationale": (
            "The RRC's own layout manual is explicit that its API number 'DOES NOT REFER TO"
            " American Petroleum Institute' and is eight digits: three county, five well, with"
            " no state prefix and no wellbore positions. Both the GIS layers and the wellbore"
            " export ship a field literally named API10 that is not one - on the arc layer it is"
            " the eight digits with a two-character wellbore code appended. TX is API state code"
            " 42, which is not the FIPS code for Texas (48), so the prefix is a rule and never a"
            " slice of something that looks like it already has it."
        ),
        "evidence_url": EWA_MANUAL,
    },
    {
        "rule_id": "cr_tx_wellbore_key_1",
        "source_id": "tx_gis_wells_county",
        "stage": "join",
        "rule_kind": "key_composite",
        "applies_to_fields": ["api10", "stcode"],
        "spec": {
            "source_cols": ["api10", "stcode"],
            "target_col": "geom_key",
            "separator": "_",
            "on_missing": "quarantine",
            "reason_code": "key_incomplete",
        },
        "rule": "A well arc is keyed by API-10 and the RRC wellbore code, never by API-10 alone.",
        "rationale": (
            "The arc layer carries one row per wellbore, and a re-entered or sidetracked well"
            " has several: the code is the RRC's own STCODE (H1, H2, S1 and so on). Keying arcs"
            " on API-10 would collapse a multi-lateral well to one geometry and lose the rest,"
            " which is the failure cr_nd_multilateral_1 exists to prevent in ND. API-12 is not"
            " available here - TX publishes a letter-and-digit wellbore code, not the numeric"
            " suffix PPDM defines - so the key says what it is rather than implying a standard."
        ),
        "evidence_url": GIS_LINK,
    },
    {
        "rule_id": "cr_tx_nad27_1",
        "source_id": "tx_gis_wells_county",
        "stage": "conform",
        "rule_kind": "datum_transform",
        "applies_to_fields": ["longitude", "latitude", "geom"],
        "spec": {
            "source_epsg": 4267,
            "target_epsg": 4326,
            "detect": {
                "prj_contains": "GCS_North_American_1927",
                "accepted_epsg": [4267],
                "reject_reason_code": "datum_undetermined",
            },
            "pipeline": NAD27_PIPELINE,
            "grid_source_id": "proj_grid_nad27",
            "grid_sha256": (
                "44611d823c48e5347500ee6afe40ff33d2b88cf817bf59f705ed4a4c3bd687d7"
            ),
            "truth_columns": {"lon": "long83", "lat": "lat83"},
            "truth_tolerance_m": 1.0,
            "untransformed_floor_m": 20.0,
        },
        "rule": (
            "Transform RRC NAD27 coordinates to EPSG:4326 through the pinned NADCON grid, and"
            " never through a three-parameter fit."
        ),
        "rationale": (
            "Every .prj in the 2026-08-20 county well layers reads GCS_North_American_1927 /"
            " Clarke_1866, which is EPSG:4267, matching the RRC GIS FAQ's own statement of the"
            " datum. The shift is not cosmetic: over 4,000 Andrews county surface points the"
            " untransformed positions sit a median 43.64 m (min 41.90, max 46.57) from the same"
            " rows' published NAD83 coordinates. PROJ's default NAD27 to WGS 84 path on a host"
            " without the NADCON grid is a three-parameter transform and leaves a median 3.40 m"
            " residual; the pinned us_noaa_conus.tif pipeline leaves a median of 0.0074 m over"
            " all 27,102 Andrews rows the RRC did convert, with 80.9 percent inside 0.1 m and"
            " 99.9 percent inside 5 m. The residual is bimodal - a cluster at zero and one at"
            " 3.4 to 3.9 m - which is the RRC's own conversion vintage differing on part of its"
            " file, not a spread in this transform; 602 further rows publish a NAD83 pair"
            " identical to their NAD27 one and were never converted upstream at all, so they"
            " are counted rather than measured. The grid therefore has its own manifest and its"
            " own hash, so a"
            " TX coordinate's explain chain terminates in checksummed bytes for the transform as"
            " well as for the data, and a host missing the grid fails rather than quietly"
            " producing a metre-scale error."
        ),
        "evidence_url": GIS_FAQ,
    },
    {
        "rule_id": "cr_tx_compute_crs_1",
        "source_id": "tx_gis_wells_county",
        "stage": "conform",
        "rule_kind": "parse_directive",
        "applies_to_fields": ["geom"],
        "spec": {
            "storage_epsg": 4326,
            "length_method": "geodesic",
            "ellipsoid": "WGS84",
            "purpose": "length_computation",
            "length_expression": "ST_Length(geom::geography)",
            "forbidden_field": "SHAPE_LEN",
        },
        "rule": (
            "Measure TX lateral length geodesically on the WGS84 ellipsoid; never project it"
            " into a UTM zone and never read the shipped SHAPE_LEN."
        ),
        "rationale": (
            "The TX instance of the decision cr_nd_compute_crs_2 made for ND, seeded rather than"
            " borrowed so a TX length's handle resolves to a TX rule with TX evidence. The"
            " Permian's projected CRS in the registry is UTM 13N, and the Midland basin reaches"
            " about a degree east of that zone, so a projected length would carry a systematic"
            " zone error for part of the basin. A geodesic length chooses no zone. SHAPE_LEN is"
            " forbidden for a different reason than ND's SHAPE_Leng: it is not degrees, it is"
            " feet on the RRC's NAD27 Texas statewide mapping system, so it would be plausible"
            " and unexplainable at once - the value glasswell serves has to be one this system"
            " computed from geometry it can show you."
        ),
        "evidence_url": GIS_LINK,
    },
    {
        "rule_id": "cr_tx_county_scope_1",
        "source_id": "tx_gis_wells_county",
        "stage": "validate",
        "rule_kind": "validity_filter",
        "applies_to_fields": ["source_county_code"],
        "spec": {
            "predicate_ast": {
                "in": [{"col": "source_county_code"}, list(PERMIAN_COUNTY_CODES)]
            },
            "on_fail": "quarantine",
            "reason_code": "out_of_scope",
            "county_codes": list(PERMIAN_COUNTY_CODES),
            "districts": ["08", "8A", "7C"],
            "district_share_floor": 0.5,
            "artifact_pattern": "well{county_code}.zip",
            "excluded_rows_recorded_as": "audit event staging.scope_excluded, with a count",
        },
        "rule": (
            "The first TX cut covers the county files whose wells are majority RRC district 08,"
            " 8A or 7C; the rest of the state is a later rule, not a later code change."
        ),
        "rationale": (
            "The Commission's own district assignment is the only Permian definition in the"
            " data: for each county code, the share of district-bearing rows in the 2026-08-20"
            " wellbore export that carry district 08, 8A or 7C. Fifty-five county codes clear"
            " half, and all but four clear 0.98. County does not determine district - 267 of 275"
            " county codes appear under more than one - so the filter is a measured majority and"
            " says so. The list is spec data because widening it is a superseding rule row with"
            " a date and a reason, which is what makes a coverage change auditable rather than a"
            " diff in a parser."
        ),
        "evidence_url": EWA_LINK,
    },
    {
        "rule_id": "cr_tx_ewa_layout_1",
        "source_id": "tx_wellbore_ewa_csv",
        "stage": "parse",
        "rule_kind": "parse_directive",
        "applies_to_fields": ["all"],
        "spec": {
            "format": "csv",
            "delimiter": ",",
            "header_policy": "none",
            "field_count": 59,
            "layout_url": EWA_MANUAL,
            "layout_sha256": (
                "b6ad3c8556c45555d054f9b86d0dce77593147390c0ccce1ed12ac5708655264"
            ),
            "fields": {
                "district_no": 1,
                "county_code": 2,
                "api": 3,
                "county_name": 4,
                "oil_gas_code": 5,
                "lease_name": 6,
                "field_no": 7,
                "field_name": 8,
                "lease_no": 9,
                "well_no": 10,
                "operator_name": 12,
                "operator_no": 13,
                "total_depth_ft": 16,
                "well_type_name": 19,
                "plug_date": 21,
                "on_schedule": 27,
                "wellbore_id": 28,
                "completion_date": 31,
            },
            "assertions": {
                "county_code_is_api_prefix": {"county_code": 2, "api": 3, "width": 3},
                "oil_gas_code_domain": ["O", "G", "A", ""],
            },
        },
        "rule": (
            "The export ships no header; read it positionally against the RRC layout manual's"
            " field numbers, and prove the pin on every record before promoting any of it."
        ),
        "rationale": (
            "OG_WELLBORE_EWA_Report.csv has 59 comma-separated fields and no header row, so a"
            " positional layout is the only way to read it and a wrong layout would parse"
            " cleanly into plausible nonsense - the failure mode SB-01 P7b-T3 opens for the"
            " fixed-width wellbore master. The field numbers are the manual's own, and the"
            " layout is checked against the data rather than trusted: the county code in field 2"
            " equals the first three characters of the API in field 3 for all 1,310,392 records"
            " of the 2026-08-20 export, and field 5 holds only O, G or blank. A record that"
            " fails either assertion, or that does not have 59 fields, is quarantined as"
            " schema_mismatch instead of being read under a layout it has just disproved."
        ),
        "evidence_url": EWA_MANUAL,
    },
    {
        "rule_id": "cr_tx_ewa_scope_1",
        "source_id": "tx_wellbore_ewa_csv",
        "stage": "parse",
        "rule_kind": "parse_directive",
        "applies_to_fields": ["all"],
        "spec": {
            "scope_field": "county_code",
            "county_codes": list(PERMIAN_COUNTY_CODES),
            "county_scope_rule": "cr_tx_county_scope_1",
            "excluded_rows_recorded_as": "audit event staging.scope_excluded, with a count",
        },
        "rule": (
            "Stage the wellbore export's records for the counties in scope; count the rest into"
            " the parse derivation rather than dropping them unmentioned."
        ),
        "rationale": (
            "The export is one statewide artifact, so the county scope cannot be expressed by"
            " fetching less of it. Excluded records are not rejects and are not quarantined -"
            " nothing about them failed - but a silent exclusion would make the staged row count"
            " unreadable, so the count and the scope rule are on the parse derivation and on an"
            " audit event. The raw bytes are retained and their hash is the manifest's, so"
            " widening the scope is a re-parse rather than a re-fetch."
        ),
        "evidence_url": EWA_LINK,
    },
    {
        "rule_id": "cr_tx_lease_key_1",
        "source_id": "tx_wellbore_ewa_csv",
        "stage": "join",
        "rule_kind": "key_composite",
        "applies_to_fields": ["oil_gas_code", "district_no", "lease_no"],
        "spec": {
            "source_cols": ["oil_gas_code", "district_no", "lease_no"],
            "target_col": "lease_key",
            "separator": "-",
            "pad": {"lease_no": 6},
            "on_missing": "quarantine",
            "reason_code": "key_incomplete",
            "uniqueness_scope": "district",
        },
        "rule": "A TX lease is keyed by (oil_gas_code, district_no, lease_no), never by lease_no.",
        "rationale": (
            "The RRC defines LEASE_NO as unique within a district only, and the 2026-08-20"
            " export proves it: 33,868 of 348,293 lease numbers (9.7 percent) appear under more"
            " than one (oil/gas code, district) pair. Seeded now, five phases before TX"
            " production is ingested, because the allocation join is where a bare lease number"
            " would silently merge two leases' wells and there would be nothing in the output to"
            " show it had happened."
        ),
        "evidence_url": EWA_LINK,
    },
    {
        "rule_id": "cr_tx_status_vocab_1",
        "source_id": "tx_wellbore_ewa_csv",
        "stage": "conform",
        "rule_kind": "vocab_map",
        "applies_to_fields": ["well_type_name"],
        "spec": {
            "mapping_table": "tx_status_map",
            "key_col": "status_input",
            "value_col": "status_canonical",
            "unmapped_action": "quarantine",
            "reason_code": "unknown_status",
        },
        "rule": (
            "Map the RRC WELL_TYPE_NAME vocabulary onto the canonical status vocabulary through"
            " lineage.tx_status_map; an unlisted value is quarantined, never guessed."
        ),
        "rationale": (
            "WELL_TYPE_NAME is what a wellbore is used for, and the manual enumerates"
            " twenty-three values; twenty of them appear in the Permian counties. Eleven"
            " describe service rather than production, so they map to a service class rather"
            " than to active - injection alone is 24,710 rows in scope, and painting those green"
            " beside producers would misstate what the map shows. A blank value is not an"
            " unknown one: the source reported nothing, the well keeps a null status, and the"
            " legend shows it as unmapped rather than the pipeline inventing a class."
        ),
        "evidence_url": EWA_MANUAL,
    },
    {
        "rule_id": "cr_tx_plugged_precedence_1",
        "source_id": "tx_wellbore_ewa_csv",
        "stage": "conform",
        "rule_kind": "parse_directive",
        "applies_to_fields": ["plug_date", "well_type_name"],
        "spec": {
            "precedence_field": "plug_date",
            "precedence_token": "PLUGGED",
            "target_field": "status_input",
        },
        "rule": "A wellbore with a plugging date on file is plugged, whatever its well type says.",
        "rationale": (
            "PLUG_DATE is the date on the W-3 plugging report, and the type field is not"
            " re-stated when a well is plugged - 32.2 percent of the APIs in scope carry a plug"
            " date while only 57.0 percent carry any well type at all. Taking the plugging"
            " record first is both correct and the difference between a status on 57 percent of"
            " wells and one on 88.6 percent of them. The sentinel is spec data so the token that"
            " reaches the vocabulary table is the rule's, not a literal in the promotion."
        ),
        "evidence_url": EWA_MANUAL,
    },
    {
        "rule_id": "cr_tx_ewa_role_1",
        "source_id": "tx_wellbore_ewa_csv",
        "stage": "join",
        "rule_kind": "code_ref",
        "applies_to_fields": ["lease_key"],
        "spec": {
            "link_role": "validator_a",
            "canonical_crosswalk": "OG_WELL_COMPLETION (tx_pdq_dsv)",
            "merge_forbidden": True,
            "module_function": "glasswell.ingest.tx_wellbore:_promote_lease_links",
            "contract_note": (
                "Writes canonical.well_lease_links with link_role validator_a and never"
                " updates a row another crosswalk wrote."
            ),
        },
        "rule": (
            "The wellbore export is Validator A for the well-to-lease link; it is recorded"
            " beside the canonical crosswalk and never merged into it."
        ),
        "rationale": (
            "Two regulator-published crosswalks that agree prove nothing once they have been"
            " averaged, and their disagreement is the only measurement of allocation error this"
            " system will have. OG_WELL_COMPLETION inside the PDQ dump is the canonical"
            " crosswalk; these links carry link_role validator_a so that when the PDQ path lands"
            " the two can be compared rather than reconciled by whichever ran last."
        ),
        "evidence_url": EWA_LINK,
    },
    {
        "rule_id": "cr_tx_allocation_scope_1",
        "source_id": "tx_wellbore_ewa_csv",
        "stage": "validate",
        "rule_kind": "code_ref",
        "applies_to_fields": ["production"],
        "spec": {
            "jurisdiction": "TX",
            "state_code": "42",
            "reporting_level": "lease",
            "allocation_required": True,
            "well_level_production_served": False,
            "module_function": "glasswell.lineage.conformance:lease_reporting_rule",
            "contract_note": (
                "The API reads this rule to decide whether a well's jurisdiction reports at the"
                " lease, and serves the disclosure instead of an empty production series."
            ),
            "measured": {
                "oil_leases": 207094,
                "oil_wells_per_lease_mean": 3.63,
                "oil_leases_with_more_than_one_well": 0.404,
                "gas_leases": 283043,
                "gas_wells_per_lease_mean": 1.01,
            },
        },
        "rule": (
            "TX production is reported at the lease. No well-level TX volume is served until"
            " allocation ships with its error bounds, and a TX well card says so rather than"
            " showing an empty chart."
        ),
        "rationale": (
            "The Commission states it plainly - production is reported by lease rather than by"
            " individual well - and DIR-3 rules that canonical carries observations at native"
            " granularity only, so a well-level TX series is a derived artifact and cannot"
            " appear beside ND's observed ones without a granularity flag and an error bound."
            " The scale of the problem is measured on the 2026-08-20 export: oil leases average"
            " 3.63 wells and 40.4 percent carry more than one, while 98.8 percent of gas leases"
            " carry exactly one, which is why allocation is an oil-lease problem. Until then the"
            " honest state on a TX well is 'pending allocation', not 'no production reported'."
        ),
        "evidence_url": DOWNLOADS_PAGE,
    },
    {
        "rule_id": "cr_tx_gis_layers_1",
        "source_id": "tx_gis_wells_county",
        "stage": "parse",
        "rule_kind": "parse_directive",
        "applies_to_fields": ["all"],
        "spec": {
            "archive_pattern": "well{county_code}.zip",
            "layers": {"surface": "s", "bottomhole": "b", "lines": "l"},
            "optional_layers": ["lines"],
            "prj_per_layer": True,
        },
        "rule": (
            "Each county archive holds three shapefiles - surface points, bottom-hole points and"
            " well arcs - selected by the last character of the member's stem."
        ),
        "rationale": (
            "well003.zip carries well003s, well003b and well003l, each with its own .prj, so a"
            " reader that takes the first .shp it finds gets one of the three at random"
            " depending on zip order. The arcs are the TX lateral geometry: there is no free"
            " parseable TX directional survey station data at all, only images and a W-12"
            " segment with form-header fields, so this layer is the substitute and the card says"
            " so rather than implying a survey trace. The arcs layer is optional and four of the"
            " 54 archives in scope on 2026-08-20 - Bee, Brooks, El Paso and Kimble - ship none,"
            " which is a county with no horizontal wells rather than a truncated download; the"
            " surface and bottom-hole layers are not optional and their absence is an error."
        ),
        "evidence_url": GIS_LINK,
    },
    {
        "rule_id": "cr_tx_mft_resolve_1",
        "source_id": "tx_gis_wells_county",
        "stage": "parse",
        "rule_kind": "parse_directive",
        "applies_to_fields": ["all"],
        "spec": {
            "acquisition_method": "mft_guid_resolve",
            "gis_link": GIS_LINK,
            "ewa_link": EWA_LINK,
            "listing_page_rows": 5000,
            "page_cap": 250,
            "completeness_check": "declared_row_count",
        },
        "rule": (
            "Resolve an RRC artifact through its GoAnywhere listing, and refuse a listing that"
            " returns fewer rows than it declares."
        ),
        "rationale": (
            "The links are opaque GUIDs into a JSF portal with no stable file URLs, so the"
            " listing is the evidence of what was on offer and its hash is how a rotated GUID"
            " becomes a visible change. The listing also paginates at 250 rows while the well"
            " folder holds 255: reading the first page loses well501 through wellFED, which"
            " includes Yoakum county and its 14,090 wellbore records. The count the page"
            " declares is checked against the rows that arrive, because this is a failure that"
            " otherwise looks exactly like a county with no wells."
        ),
        "evidence_url": DOWNLOADS_PAGE,
    },
)

_INSERT_SOURCE = """
insert into lineage.sources (source_id, name, jurisdiction, license_note, redistributable)
values (%(source_id)s, %(name)s, %(jurisdiction)s, %(license_note)s, %(redistributable)s)
on conflict do nothing
"""

_INSERT_RULE = """
insert into lineage.conformance_rules
    (rule_id, rule_family, supersedes_rule_id, source_id, stage, applies_to_fields, rule_kind,
     spec, rule, rationale, evidence_url, effective_from)
values (%(rule_id)s, %(rule_family)s, %(supersedes_rule_id)s, %(source_id)s, %(stage)s,
        %(applies_to_fields)s, %(rule_kind)s, %(spec)s, %(rule)s, %(rationale)s,
        %(evidence_url)s, %(effective_from)s)
on conflict (rule_id) do nothing
"""


def _family(rule_id: str) -> str:
    """`cr_tx_nad27_1` belongs to family `cr_tx_nad27`: the trailing instance number is dropped."""
    head, _, tail = rule_id.rpartition("_")
    return head if tail.isdigit() else rule_id


def seed_sources_tx(connection: psycopg.Connection) -> int:
    with connection.cursor() as cursor:
        cursor.executemany(_INSERT_SOURCE, TX_SOURCES)
    return len(TX_SOURCES)


def seed_conformance_tx(connection: psycopg.Connection) -> int:
    seed_sources_tx(connection)
    payload = [
        {
            "rule_id": rule["rule_id"],
            "rule_family": _family(str(rule["rule_id"])),
            "supersedes_rule_id": rule.get("supersedes_rule_id"),
            "source_id": rule["source_id"],
            "stage": rule["stage"],
            "applies_to_fields": list(rule["applies_to_fields"]),  # type: ignore[arg-type]
            "rule_kind": rule["rule_kind"],
            "spec": Jsonb(rule["spec"]),
            "rule": rule["rule"],
            "rationale": rule["rationale"],
            "evidence_url": rule.get("evidence_url"),
            "effective_from": rule.get("effective_from", EFFECTIVE_FROM),
        }
        for rule in TX_RULES
    ]
    with connection.cursor() as cursor:
        cursor.executemany(_INSERT_RULE, payload)
        cursor.execute(
            "select count(*) from lineage.conformance_rules where rule_id like 'cr_tx_%'"
        )
        return int(cursor.fetchone()[0])
