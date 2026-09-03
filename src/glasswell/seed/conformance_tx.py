"""The TX conformance registry and source rows (SB-07 §6.2, SB-01 §2.8/§2.9).

Every rule here was established against files opened during the TX slice, and every count in a
rationale was measured on them: the 2026-08-20 county well layers and the 2026-08-20
`OG_WELLBORE_EWA_Report.csv` (1,310,392 records).
"""

from __future__ import annotations

from datetime import date

import psycopg
from psycopg.types.json import Jsonb

from glasswell.ingest.tx_mft import LISTING_PAGE_ROWS

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

# The allocation train's own valid time. Later than the slice's, because cr_tx_production_grain_1
# supersedes a rule the slice published and a successor at the same instant would not resolve.
PDQ_EFFECTIVE_FROM = date(2026, 9, 2)

PDQ_LINK = "https://mft.rrc.texas.gov/link/1f5ddb8d-329a-4459-b7f8-177b4f5ee60d"
W10_LINK = "https://mft.rrc.texas.gov/link/af355cae-e78b-4337-aba8-7ce57073dba3"
G10_LINK = "https://mft.rrc.texas.gov/link/1363c373-fe71-4044-aa23-3c90cd162ff9"
PDQ_MANUAL = "https://www.rrc.texas.gov/media/50ypu2cg/pdq-dump-user-manual.pdf"
PDQ_FAQ = (
    "https://www.rrc.texas.gov/about-us/faqs/oil-gas-faq/"
    "production-data-query-system-faqs/"
)

# The versioned artifact that computes a share, distinct from the R8 decision that admits it.
# Imported by the Texas mart and the Montana back-test so bed and consumer run identical code.
ALLOCATION_MODEL_ID = "alloc_v0_2026_09"

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
        "source_id": "tx_pdq_dsv",
        "name": "TX RRC Production Data Query dump (PDQ_DSV.zip)",
        "jurisdiction": "TX",
        "license_note": TX_LICENSE_NOTE,
        "redistributable": False,
    },
    {
        "source_id": "tx_w10_wlf607",
        "name": "TX RRC Oil Well Status, 26 Month W-10 (wlf607.ebc[.gz])",
        "jurisdiction": "TX",
        "license_note": TX_LICENSE_NOTE,
        "redistributable": False,
    },
    {
        "source_id": "tx_g10_gse10",
        "name": "TX RRC Gas Well Status, 26 Month G-10 (gse10.ebc[.gz])",
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
            "min_width": {"api": 8},
            "charset": {"api": "digits"},
            "on_missing": "quarantine",
            "reason_code": "key_incomplete",
            "state_code": "42",
        },
        "rule": "API-10 is '42' followed by the RRC's eight-digit county-plus-well number.",
        "rationale": (
            "The RRC's own layout manual is explicit that its API number 'DOES NOT REFER TO"
            " American Petroleum Institute' and is eight digits: three county, five well, with"
            " no state prefix and no wellbore positions. The bottom-hole and arc layers ship a"
            " field literally named API10 that is not one - the same eight digits, with a"
            " two-character wellbore code appended on the arcs; the surface layer has no such"
            " field, and the export's is API_NO. TX is API state code 42, which is not the FIPS"
            " code for Texas (48), so the prefix is a rule and never a slice of something that"
            " looks like it already has it. min_width is 8 and it is load-bearing: the RRC ships"
            " county plot points whose API field holds the three-digit county code alone -"
            " 78,856 of 794,826 point rows across the 55 archives are not eight characters - and"
            " padding one of those up builds a syntactically perfect API-10 for a well that does"
            " not exist. Those rows quarantine as key_incomplete, which is what they always"
            " were. charset bounds the other half of the same guarantee: eight characters is a"
            " width and 42ABCDEFGH satisfies it, so the segment is declared numeric rather than"
            " merely eight long. One value in the 55 archives is non-numeric ('475W3', which"
            " min_width already refuses) so this changes no TX row - it is stated because the"
            " same executor keys NM next, on components that are alphanumeric."
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
        "rule_id": "cr_tx_geometry_survivor_1",
        "source_id": "tx_gis_wells_county",
        "stage": "conform",
        "rule_kind": "code_ref",
        "applies_to_fields": ["api10", "geom_key"],
        "spec": {
            "keeps": "first_by_source_row_ordinal",
            "reason_code": "duplicate_row",
            "payload_fields": [
                "lon", "lat", "promoted_lon", "promoted_lat", "metres_from_promoted"
            ],
            "module_function": "glasswell.ingest.tx_gis:_promote_points",
            "contract_note": (
                "One geometry per (api10, geom_type, geom_key). The displaced row is"
                " quarantined with both positions and the distance between them."
            ),
        },
        "rule": (
            "Where two features claim one well's geometry key, the first in source order is"
            " promoted and the other is quarantined with both positions recorded."
        ),
        "rationale": (
            "The canonical key is (api10, geom_type, geom_key) and the RRC ships more than one"
            " feature under it: a well with two surface plots, or two bottom-holes carrying the"
            " same wellbore code. Something has to lose, so the choice is a rule rather than an"
            " accident of iteration order, and the losing row keeps its coordinates in the"
            " payload. Without them a reader of /v1/quarantine sees the word duplicate and"
            " cannot tell a re-survey a metre away from two records tens of kilometres apart -"
            " which is exactly what the ledger looked like before the API-10 key was fixed, when"
            " a median 'duplicate' was 35 km from the row that displaced it because both had"
            " been given a fabricated identity."
        ),
        "evidence_url": GIS_LINK,
    },
    {
        "rule_id": "cr_tx_multi_wellbore_1",
        "source_id": "tx_gis_wells_county",
        "stage": "validate",
        "rule_kind": "code_ref",
        "applies_to_fields": ["api10", "stcode"],
        "spec": {
            "detection_source": "RRC wellbore code (STCODE) on the bottom-hole and arc layers",
            "keys_on": "api12_equivalent",
            "reason_code": "multi_wellbore_policy",
            "module_function": "glasswell.ingest.tx_gis:_flag_multi_wellbore",
            "contract_note": (
                "Emits one quarantine row per API-10 carrying more than one wellbore code,"
                " naming the codes. It removes no geometry: every wellbore is still promoted."
            ),
        },
        "rule": (
            "A TX API-10 carrying more than one RRC wellbore code is a multi-wellbore well, and"
            " is measured on those codes rather than on how many times the export lists it."
        ),
        "rationale": (
            "v0.6 §3.0.5 keys sidetrack detection on API-12 because API-14 is convention rather"
            " than standard. TX publishes no API-12: it publishes a two-character wellbore code"
            " (H1, S1 and so on) on the bottom-hole and arc layers, which is the same fact in"
            " the regulator's own notation, and the export carries no wellbore suffix at all."
            " Counting an API-10's rows in the export therefore measures multi-completion"
            " reporting, not multi-wellbore geometry: of the 78,579 API-10s with more than one"
            " export row, the GIS layers show exactly one wellbore code for 75,563 - 96.3"
            " percent - and not one of those groups carries two different non-blank total"
            " depths, the signature of a single physical hole. What varies is the lease, the"
            " field and the oil/gas code. Measured on the codes, 3,691 of 355,583 API-10s are"
            " genuinely multi-wellbore - 1.04 percent, under the Permian's 5 percent trigger -"
            " and 726 of them have a single export row, so the export-side count missed them"
            " entirely while reporting a rate five times the trigger."
        ),
        "evidence_url": GIS_LINK,
    },
    {
        "rule_id": "cr_tx_identity_collapse_1",
        "source_id": "tx_wellbore_ewa_csv",
        "stage": "validate",
        "rule_kind": "code_ref",
        "applies_to_fields": ["api10"],
        "spec": {
            "reason_code": "multi_completion",
            "prefer": ["plug_date", "on_schedule", "completion_date", "source_row_ordinal"],
            "module_function": "glasswell.ingest.tx_wellbore:_identity_rows",
            "contract_note": (
                "One identity row per API-10. The records that lose are quarantined as"
                " multi_completion. The promotion judges the fields this list names, in this"
                " order, and refuses a list naming a field it cannot judge."
            ),
        },
        "rule": (
            "canonical.wells holds one row per API-10 per vintage; the export's further records"
            " for that wellbore are completions, and are quarantined as such."
        ),
        "rationale": (
            "The export lists a wellbore once per completion, lease and field, so 78,579 API-10s"
            " have more than one record. Those extra records are not rejects and they are not"
            " evidence of a second wellbore - see cr_tx_multi_wellbore_1, which measures that on"
            " the RRC's own wellbore codes - they are the lease-level reporting TX does. This"
            " slice models the wellbore, so it keeps one record and says plainly what happened"
            " to the others rather than labelling them with a policy they do not evidence."
            " A record carrying a plugging date is preferred first, because"
            " cr_tx_plugged_precedence_1 makes that date the well's status and a record"
            " discarded here is a record that rule never reads: with the on-schedule flag"
            " ranked above it, 2,157 wells are drawn active, service, inactive or temporarily"
            " abandoned against a plugging date the same export carries for them - 840, 711,"
            " 536 and 70 respectively, measured on the full 55-county 2026-08-20 load. Ranking"
            " the plugging date first takes that to nil and moves those 2,157 onto the plugged"
            " class. It is paid for in completion dates: the promoted record is then sometimes"
            " the one that carries none, so the wells whose completion date sits only on a"
            " quarantined sibling rise from 1,299 to 2,346. That trade is deliberate and it is"
            " not symmetric - a missing completion date is an absence a reader can see on the"
            " card and follow into /v1/quarantine, while a well painted active over a filed"
            " plugging date is the product stating the opposite of its own source."
        ),
        "evidence_url": EWA_MANUAL,
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
            "truth_within_1m_measured": 0.7987,
            "truth_p99_ceiling_m": 5.0,
            "untransformed_floor_m": 20.0,
            "untransformed_floor_deviates_from": "SB-01 §2.8 P7b-T2 (50 m)",
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
            " The guard asserts three things, not one: the median residual against the"
            " regulator's own NAD83 and a p99 ceiling of 5 m, because a median alone would"
            " pass a transform correct for half the rows and wrong for the rest. The share"
            " inside a metre is recorded (0.7987 statewide) and not asserted: it measures how"
            " consistently the RRC converted its own file rather than how well this transform"
            " reproduces it, so it moves with the sample. The untransformed floor is 20 m"
            " where SB-01 §2.8"
            " specifies 50 m: 50 could never have passed, since the measured untransformed"
            " median is 42.6 m and the minimum over Andrews is 30.1 m, so the floor is set"
            " below the smallest real shift rather than above the median. Recorded here"
            " because a spec deviation that lives only in code is a traceability gap."
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
        "rule_id": "cr_tx_lateral_bounds_1",
        "source_id": "tx_gis_wells_county",
        "stage": "validate",
        "rule_kind": "code_ref",
        "applies_to_fields": ["geom"],
        "spec": {
            "max_length_ft": 50000,
            "reason_code": "unreliable_numeric",
            "module_function": "glasswell.ingest.tx_gis:_promote_lines",
            "contract_note": (
                "An arc measuring longer than max_length_ft is quarantined rather than"
                " promoted, so no such length reaches a card, a tile or a length statistic."
            ),
        },
        "rule": (
            "A well arc longer than 50,000 ft is not a wellbore, and is quarantined rather than"
            " served as a lateral length."
        ),
        "rationale": (
            "The arc layer is digitised map geometry, and four arcs across the 55 archives"
            " measure over 50,000 ft - the longest 317,390 ft, sixty miles, with a tortuosity of"
            " exactly 1.0, which is to say a perfectly straight sixty-mile line. The longest"
            " horizontal wells ever drilled are around 40,000 ft measured depth, so 50,000 ft"
            " leaves the real fleet untouched while refusing the digitising artifacts. The bound"
            " is one-sided on purpose: short arcs are ordinary - 3,416 measure under 500 ft,"
            " which is what a vertical well's bottom-hole trace looks like - and a lower bound"
            " would quarantine real geometry to tidy a histogram. Under DIR-1 an unbounded"
            " served length is the first number a hostile reader reaches for."
        ),
        "evidence_url": GIS_LINK,
    },
    {
        "rule_id": "cr_tx_county_scope_1",
        "source_id": "tx_gis_wells_county",
        "stage": "validate",
        "rule_kind": "validity_filter",
        "applies_to_fields": ["feature_county_code"],
        "spec": {
            "predicate_ast": {
                "in": [{"col": "feature_county_code"}, list(PERMIAN_COUNTY_CODES)]
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
            " The predicate judges the feature's own county - the first three characters of the"
            " API the RRC gave it - and not the county the archive is named for. Those disagree"
            " for 520 of the 794,826 point features, 23 of which belong to counties outside this"
            " list; scoping on the archive name compared a value against the list it had just"
            " been assigned from, so the guard could not fire, and those features landed as"
            " wells whose identity the export had already excluded on the same grounds."
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
        "rule_id": "cr_tx_ewa_measures_1",
        "source_id": "tx_wellbore_ewa_csv",
        "stage": "validate",
        "rule_kind": "validity_filter",
        "applies_to_fields": ["total_depth_ft", "completion_date"],
        "spec": {
            "fields": [
                {"field": "total_depth_ft", "reason_code": "unreliable_numeric"},
                {"field": "completion_date", "reason_code": "out_of_range_date"},
            ],
            "on_fail": "quarantine",
            "field_action": "null_field",
        },
        "rule": (
            "A non-empty TOTAL DEPTH or COMPLETION DATE the promotion's readers cannot parse is"
            " withheld from the well and recorded as a rejected value; the well still promotes."
        ),
        "rationale": (
            "cr_tx_ewa_layout_1 proves the pin - 59 fields, the county code as the API prefix,"
            " the oil-gas domain - and not one of those assertions can judge what is inside"
            " TOTAL DEPTH or COMPLETION DATE. A thousands separator in the depth, or a switch to"
            " MM/DD/YYYY in the date, passes the layout and is then unreadable to the readers"
            " this promotion applies. Promoting that as null files the Commission's answer as an"
            " absence and the ledger loses the difference between a field the RRC left blank and"
            " a field this pipeline could not read - the distinction the reject discipline exists"
            " to make (SB-01 P7b-T3). The reject is the value and not the row: the API-10, the"
            " operator and the status beside it are separate filings, and a defective depth is no"
            " evidence against them, which is the reasoning cr_nd_survey_station_range_1 already"
            " records for ND. field_action and the per-field reason codes are read by the loader"
            " rather than described by it - null_field is the only action this promotion can"
            " execute, and it refuses a rule that asks for another - so changing what a"
            " withholding does here has to be a new rule row and not an edit in tx_wellbore.py."
        ),
        "evidence_url": EWA_MANUAL,
    },
    {
        "rule_id": "cr_tx_operator_absence_1",
        "source_id": "tx_wellbore_ewa_csv",
        "stage": "parse",
        "rule_kind": "parse_directive",
        "applies_to_fields": ["operator_name", "operator_no"],
        "spec": {
            "normalises_to": None,
            "current_tx_wells": 359421,
            "with_operator": 289382,
            "without_operator": 70039,
            "causes": [
                {"cause": "blank_ewa_operator_field", "source_id": "tx_wellbore_ewa_csv",
                 "wells": 39390},
                {"cause": "no_ewa_wellbore_record", "source_id": "tx_gis_wells_county",
                 "wells": 30649},
            ],
        },
        "rule": (
            "A TX well with no operator name is a well the Commission's files did not report one"
            " for. It is never withheld, never imputed, and never folded into another bucket."
        ),
        "rationale": (
            "Measured on the deployed database over all 359,421 current TX wells: 289,382 carry"
            " an operator and 70,039 do not, in two populations that do not overlap. 39,390 were"
            " promoted from an EWA wellbore record whose operator field is empty; 30,649 reached"
            " canonical from a county GIS layer and have no EWA wellbore record at all, so no"
            " operator was ever carried by the source that created them. Neither is withholding:"
            " cr_tx_ewa_measures_1 is the only TX withholding rule and it covers TOTAL DEPTH and"
            " COMPLETION DATE, stating explicitly that the operator beside them is a separate"
            " filing. Texas has no operator registry comparable to NM's OGRID and"
            " lineage.operator_aliases carries no TX row, so an absent name cannot be recovered"
            " by lookup and is not guessed. The distinction matters because /v1/wells/facets"
            " counts wells by operator: were this absence ranked as a value it would outrank"
            " every real operator in the state, and were it dropped the buckets would not sum to"
            " the population."
        ),
        "evidence_url": EWA_MANUAL,
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
            " The scale of the problem is measured on the 2026-08-20 export, per distinct"
            " API-10 - this project's identity spine, and the basis its own"
            " one-wellbore-per-API-10 policy asserts: 207,094 oil leases average 3.39 wells and"
            " 38.3 percent carry more than one, while all 283,043 gas leases carry exactly one."
            " Counted per export record instead, the same figures read 3.63, 40.4 percent and"
            " 98.8 percent - the export lists a wellbore once per completion, so that basis"
            " overstates the oil case and understates how clean the gas case is. Either way"
            " allocation is an oil-lease problem. Until it ships, the honest state on a TX well"
            " is 'pending allocation', not 'no production reported'."
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
            " 55 archives in scope on 2026-08-20 - Bailey, Concho, El Paso and Kimble, named"
            " from the export's own county-code table - ship none,"
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
            "listing_page_rows": LISTING_PAGE_ROWS,
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
            " otherwise looks exactly like a county with no wells. listing_page_rows is the"
            " constant the resolver uses rather than a copy of it, and it must be one of the"
            " sizes the portal's own control offers: asking for anything else comes back as"
            " IllegalArgumentException rather than a page."
        ),
        "evidence_url": DOWNLOADS_PAGE,
    },
    {
        "rule_id": "cr_tx_basin_scope_1",
        "source_id": "tx_gis_wells_county",
        "stage": "conform",
        "rule_kind": "code_ref",
        "applies_to_fields": ["basin"],
        "spec": {
            "module_function": "glasswell.marts.wells:refresh_for",
            "contract_note": (
                "the Texas wells mart resolves its lateral length through the permian row in"
                " lineage.crs_registry, and this row is where that basin is named"
            ),
            "basin": "permian",
        },
        "rule": "Texas's served geometry is scoped to the Permian basin.",
        "rationale": (
            "cr_tx_county_scope_1 narrows the slice to the 55 Permian-district counties, so the"
            " basin is a property of what was loaded rather than a claim about the state. The"
            " mart carried it as a module constant, which no reader could cite and no"
            " supersession could reach; registered here it is a row, and lineage.crs_registry"
            " already holds the permian entry it resolves to."
        ),
        "evidence_url": DOWNLOADS_PAGE,
    },
    {
        "rule_id": "cr_tx_length_source_1",
        "source_id": "tx_gis_wells_county",
        "stage": "conform",
        "rule_kind": "code_ref",
        "applies_to_fields": ["lateral_length_ft"],
        "spec": {
            "module_function": "glasswell.marts.wells:refresh_for",
            "contract_note": (
                "a Texas lateral is measured under the compute-CRS rule lineage.crs_registry"
                " names for the basin cr_tx_basin_scope_1 registers, and the served figure"
                " cites that rule's id"
            ),
            "basin": "permian",
        },
        "rule": "A Texas lateral is measured under the compute-CRS rule its registered basin"
        " resolves to.",
        "rationale": (
            "Texas resolves through the basin rather than naming a source directly, because"
            " lineage.crs_registry is keyed by basin and already answers the question: the"
            " permian row names tx_gis_wells_county and cr_tx_compute_crs_1 is what measures"
            " the arc. Naming the source here as well would be a second copy of an answer the"
            " registry already gives, and the two would drift the first time a zone moved."
        ),
        "evidence_url": DOWNLOADS_PAGE,
    },
    {
        "rule_id": "cr_tx_pdq_format_1",
        "source_id": "tx_pdq_dsv",
        "stage": "parse",
        "rule_kind": "parse_directive",
        "applies_to_fields": ["all"],
        "spec": {
            "delimiter": "}",
            "header_row": 1,
            "enclosure": None,
            "archive_format": "zip64_deflate",
            "member_selection": "by_name",
            "members_read": [
                "GP_COUNTY_DATA_TABLE.dsv",
                "GP_DATE_RANGE_CYCLE_DATA_TABLE.dsv",
                "GP_DISTRICT_DATA_TABLE.dsv",
                "OG_LEASE_CYCLE_DATA_TABLE.dsv",
                "OG_WELL_COMPLETION_DATA_TABLE.dsv",
                "OG_REGULATORY_LEASE_DW_DATA_TABLE.dsv",
            ],
            "members_excluded": [
                "OG_COUNTY_CYCLE_DATA_TABLE.dsv",
                "OG_COUNTY_LEASE_CYCLE_DATA_TABLE.dsv",
            ],
            "on_header_change": "refuse",
            "passes": 2,
        },
        "rule": (
            "The dump is a `}`-delimited text archive with one header row and no enclosure."
            " The six members read are selected by name; a member whose header gains or loses"
            " a column refuses the parse rather than quarantining a row."
        ),
        "rationale": (
            "Selecting members by ordinal would silently re-map every column the month the RRC"
            " adds a table, and the two county members are excluded because the manual"
            " describes them as estimates - `OG_COUNTY_CYCLE` and `OG_COUNTY_LEASE_CYCLE` read"
            " 'This is an estimate only based on allowables and potentials' and every CNTY_"
            " dictionary entry ends 'This is an estimated value.' The largest of them is 12.7"
            " GB uncompressed and is one we do not want. A header change invalidates the row"
            " mapping rather than one row, so quarantining is the wrong shape: nothing failed"
            " to parse, the file stopped being the file the rule describes. The FAQ's stale"
            " sentence that the Production Database can be purchased is contradicted by the"
            " free downloads page, the live listing and the measured stream, and is recorded"
            " here so it is not rediscovered as a licence bar."
        ),
        "evidence_url": PDQ_MANUAL,
        "effective_from": PDQ_EFFECTIVE_FROM,
    },
    {
        "rule_id": "cr_tx_pdq_scope_1",
        "source_id": "tx_pdq_dsv",
        "stage": "parse",
        "rule_kind": "parse_directive",
        "applies_to_fields": ["district_no", "lease_no", "api10"],
        "spec": {
            "scope_applied_at": "promotion",
            "scope_source": "OG_WELL_COMPLETION",
            "county_codes": list(PERMIAN_COUNTY_CODES),
            "excluded_rows_recorded_as": "audit event staging.scope_excluded, with a count",
            "quarantine": False,
        },
        "rule": (
            "The county scope is applied at promotion, not at parse: OG_LEASE_CYCLE carries no"
            " county, so the in-scope lease set is derived from OG_WELL_COMPLETION and"
            " out-of-scope rows are counted rather than quarantined."
        ),
        "rationale": (
            "Filtering at parse would need a county the lease member does not carry, so the"
            " parse would have to hold the whole crosswalk in memory before it could stage a"
            " row. Pass one reads the small members and the crosswalk and builds the allowlist;"
            " pass two stages the lease member column-projected and unfiltered; promotion"
            " applies the allowlist. Both passes read one on-disk artifact under one manifest"
            " and one sha256. A row outside the scope did not fail: it is a row about a well"
            " this deployment does not hold, which is the audit-event shape cr_tx_ewa_scope_1"
            " already set for the sibling artifact."
        ),
        "evidence_url": PDQ_MANUAL,
        "effective_from": PDQ_EFFECTIVE_FROM,
    },
    {
        "rule_id": "cr_tx_production_grain_1",
        "supersedes_rule_id": "cr_tx_allocation_scope_1",
        "source_id": "tx_pdq_dsv",
        "stage": "validate",
        "rule_kind": "code_ref",
        "applies_to_fields": ["production"],
        "spec": {
            "jurisdiction": "TX",
            "state_code": "42",
            "reporting_level": "lease",
            "allocation_required": True,
            "well_level_production_served": True,
            "no_water_stream": True,
            "completeness_lag_months": 6,
            "grains": {
                "O": "lease over one or more wells",
                "G": "one gas well per lease",
            },
            "module_function": "glasswell.lineage.conformance:lease_reporting_rule",
            "contract_note": (
                "The API reads this rule to decide whether a well's jurisdiction reports at the"
                " lease and whether a well-level figure is nonetheless served. Texas now serves"
                " one, as an allocation that says so on every point."
            ),
        },
        "rule": (
            "TX production is filed at the lease and a well-level TX volume is now served as an"
            " allocation, labelled as one. OIL_GAS_CODE 'G' rows are already per well; 'O' rows"
            " are lease-grain over one or more wells. No water column exists, so Texas serves"
            " two streams, and the last six months of every chart are systematically"
            " under-filed."
        ),
        "rationale": (
            "The successor to cr_tx_allocation_scope_1, which said no well-level TX volume"
            " would be served until allocation shipped with its error bounds. Allocation has"
            " shipped: the bound is a served statement that no transferable bound exists yet,"
            " naming the study rule that will close it, which is what R-06's 'ship them wide"
            " and say so' means when the width is unmeasured. The third spec key is what lets"
            " one predicate have two consumers: the card stops showing a pending-allocation"
            " panel while the producing class keeps resolving Texas to unknown, because a"
            " producing class over allocated shares is a separate decision this rule does not"
            " make. The completeness lag is the Commission's own sentence: 'Historically,"
            " production records are substantially complete after about six months.'"
        ),
        "evidence_url": PDQ_FAQ,
        "effective_from": PDQ_EFFECTIVE_FROM,
    },
    {
        "rule_id": "cr_tx_pdq_crosswalk_1",
        "source_id": "tx_pdq_dsv",
        "stage": "join",
        "rule_kind": "key_composite",
        "applies_to_fields": ["lease_key", "api10", "district_no"],
        "spec": {
            "crosswalk_member": "OG_WELL_COMPLETION",
            "link_role": "canonical_crosswalk",
            "lease_key_rule": "cr_tx_lease_key_1",
            "api10_rule": "cr_tx_api10_build_1",
            "source_cols": ["oil_gas_code", "district_no", "lease_no"],
            "separator": "-",
            "pad": {"lease_no": 6},
            "district_key": "DISTRICT_NO",
            "district_label": "DISTRICT_NAME",
            "district_map": {
                "07": "6E", "08": "7B", "09": "7C", "10": "08", "11": "8A",
                "13": "09", "14": "10", "20": "State Wide",
            },
            "membership_grain": "snapshot_at_export_vintage",
            "resolution": "greatest effective_from <= resolution clock",
            "retro_delete": False,
        },
        "rule": (
            "OG_WELL_COMPLETION is the canonical crosswalk: it carries the lease key and the"
            " API-10 parts in one row, so lease-to-well is exact and in-dump. Membership is a"
            " snapshot at an export vintage, resolved as the greatest effective_from at or"
            " before the resolution clock, and no later vintage retro-deletes a month already"
            " resolved at an earlier one."
        ),
        "rationale": (
            "District numbering is two vocabularies in one file - GP_DISTRICT measured 07 as"
            " 6E, 08 as 7B, 09 as 7C, 10 as 08, 11 as 8A, 13 as 09, 14 as 10 and 20 as State"
            " Wide - so a join on the name silently crosses districts and the key is always"
            " DISTRICT_NO. LEASE_NO is VARCHAR2(6) in PDQ, PIC 9(5) in the W-10 file and padded"
            " to 6 in the EWA export, so it is padded before any comparison. canonical"
            " .well_lease_links has no effective_to, no month grain and no on-lease date, so"
            " membership cannot be a per-month fact and pretending otherwise would be a claim"
            " the data does not carry."
        ),
        "evidence_url": PDQ_MANUAL,
        "effective_from": PDQ_EFFECTIVE_FROM,
    },
    {
        "rule_id": "cr_tx_allocation_v0_1",
        "source_id": "tx_pdq_dsv",
        "stage": "conform",
        "rule_kind": "code_ref",
        "applies_to_fields": ["volume", "granularity", "allocation_class"],
        "spec": {
            "allocation_model_id": ALLOCATION_MODEL_ID,
            "module_function": "glasswell.allocation.v0:allocate_lease_month",
            "method": "equal_share_sign_aware",
            "remainder_to": "lowest_api10",
            "allocation_classes": [
                "observed_gas_well",
                "observed_single_well_lease",
                "allocated_equal_share",
                "allocated_after_status_change",
                "excluded_after_plug",
                "unallocated",
            ],
            "eligibility": (
                "resolved membership assigns the well to the lease, completion_date is null or"
                " on or before the production month, and plug_date is null or the production"
                " month is on or before it"
            ),
            "eligibility_source": "canonical.wells_latest",
            "undated_plugged": "eligible, labelled allocated_after_status_change",
            "redistribute_excluded": True,
            "membership_back_projection": True,
            "error_source": "cr_alloc_v0_error_bounds_1",
            "error_bounds_outcome_v0": "not_measured",
            "as_of_supported": False,
            "as_of_reason": (
                "the allocation mart holds one snapshot per key, so an older as_of would return"
                " the current allocation labelled with the caller's date"
            ),
            "unallocated_causes": [
                "no_crosswalk_row",
                "no_eligible_well",
                "all_wells_after_month",
                "negative_correction",
            ],
            "unallocated_share_degraded_at": 0.005,
            "cumulatives_grain": "well",
            "cumulatives_basis": "allocated",
        },
        "rule": (
            "A lease-month's volume is split equally among the wells eligible that month. The"
            " split is computed on abs(V): each well takes floor(abs(V)/n), the remainder goes"
            " to the eligible well with the lowest API-10, and sign(V) is applied to every"
            " share. A gas lease and a single-well oil lease pass the lease volume through as"
            " well_observed; every other share is lease_allocated and carries the model id."
            " Texas writes a well-grain cumulative row from this mart, on an allocated basis."
        ),
        "rationale": (
            "The lease volume is a fact - LEASE_OIL_PROD_VOL is the amount produced by lease as"
            " reported by the operator, with none of the estimated-value language the county"
            " tables carry - and the per-well share is an estimate, so the fact stays in"
            " canonical at its native grain and the estimate lives in a mart. Splitting on the"
            " signed value would hand the lowest-API-10 well a positive bbl in a correction"
            " month: floor(-7/2) is -4 twice, and the remainder needed to conserve is +1."
            " Conservation would not catch it, because it conserves. The dominant assumption is"
            " the back-projection: v0 holds one crosswalk vintage, so a lease's current well set"
            " is applied to its whole history, crediting wells drilled late with early months"
            " and dropping wells that left. That is the largest v0 error term and it has no"
            " number, which is why the study rule is cited rather than a band invented. The"
            " degraded threshold is half a percent because a half-percent of Texas volume with"
            " no well to carry it is a data question, and below that it is the long tail of"
            " leases whose only well predates the crosswalk."
        ),
        "evidence_url": PDQ_MANUAL,
        "effective_from": PDQ_EFFECTIVE_FROM,
    },
    {
        "rule_id": "cr_tx_liquids_basis_1",
        "source_id": "tx_pdq_dsv",
        "stage": "conform",
        "rule_kind": "code_ref",
        "applies_to_fields": ["volume", "stream"],
        "spec": {
            "basis": "oil+condensate",
            "applied_by": "glasswell",
            "canonical_streams": ["oil", "condensate"],
            "mart_stream": "liquid",
            "wire_column": "oil_bbl",
            "source_cols": ["LEASE_OIL_PROD_VOL", "LEASE_COND_PROD_VOL"],
            "disjoint_on": "OIL_GAS_CODE",
        },
        "rule": (
            "The Texas liquid stream is oil plus condensate: LEASE_OIL_PROD_VOL on oil leases"
            " and LEASE_COND_PROD_VOL on gas leases, disjoint populations keyed by"
            " OIL_GAS_CODE, so their union double-counts nothing."
        ),
        "rationale": (
            "The Commission publishes them apart and says so: 'The Railroad Commission of"
            " Texas crude oil production data reflects only crude oil produced from oil leases"
            " as reported by operators. The Commission data does not include condensate, which"
            " are liquid hydrocarbons produced from a gas well.' A reader comparing glasswell's"
            " Texas liquid figure to the RRC's published crude figure will find glasswell"
            " higher, and this rule is why - which is what the blueprint means by stating the"
            " liquids policy wherever the number appears rather than leaving the reader to"
            " discover a discrepancy they cannot explain."
        ),
        "evidence_url": PDQ_MANUAL,
        "effective_from": PDQ_EFFECTIVE_FROM,
    },
    {
        "rule_id": "cr_tx_gas_basis_1",
        "source_id": "tx_pdq_dsv",
        "stage": "conform",
        "rule_kind": "code_ref",
        "applies_to_fields": ["volume", "stream"],
        "spec": {
            "basis": "gas_well_gas+casinghead",
            "canonical_stream": "gas",
            "mart_stream": "gas",
            "wire_column": "gas_mcf",
            "source_cols": ["LEASE_GAS_PROD_VOL", "LEASE_CSGD_PROD_VOL"],
            "never_summed": ["LEASE_GAS_LIFT_INJ_VOL", "LEASE_CSGD_GAS_LIFT"],
            "disjoint_on": "OIL_GAS_CODE",
        },
        "rule": (
            "The Texas gas stream is gas-well gas plus casinghead gas, both MCF and disjoint on"
            " OIL_GAS_CODE. The two gas-lift injection columns are injection and are never"
            " summed in."
        ),
        "rationale": (
            "Casinghead gas is produced with oil and is the whole gas story on an oil lease;"
            " omitting it would under-report the Permian's associated gas, which is most of it."
            " The lift columns describe gas put back down the hole, so summing them would count"
            " the same molecules twice and call re-injection production."
        ),
        "evidence_url": PDQ_MANUAL,
        "effective_from": PDQ_EFFECTIVE_FROM,
    },
    {
        "rule_id": "cr_tx_geometry_provenance_1",
        "source_id": "tx_gis_wells_county",
        "stage": "conform",
        "rule_kind": "code_ref",
        "applies_to_fields": ["geom_type", "geometry_provenance"],
        "spec": {
            "jurisdiction": "TX",
            "served_verbatim": True,
            "geom_types": {
                "surface": "RRC-filed point, transformed under cr_tx_nad27_1",
                "bottomhole": "RRC-filed point, transformed under cr_tx_nad27_1",
                "lateral": "county GIS well-arc line, a filed cartographic line",
            },
            "survey_derived": False,
            "canonical_column": "geometry_provenance",
            "served_from": "canonical.well_spatial.geom_type",
            "mirrors_rule_id": "cr_nd_geometry_provenance_1",
        },
        "rule": (
            "Texas geometry provenance is served verbatim: surface and bottomhole are"
            " RRC-filed points transformed under cr_tx_nad27_1, and a lateral is the county GIS"
            " well-arc line - a filed cartographic line, not a survey-derived path."
        ),
        "rationale": (
            "Texas had no registered geometry-provenance decision at all, so the card fell back"
            " to a default and a Texas lateral could read as though it had been derived from a"
            " directional survey. There is no free parseable Texas directional survey station"
            " data: the arc is what the Commission publishes and the card should say that is"
            " what it is drawing. The decision is a registry row rather than a dictionary in"
            " the router, so a sixth jurisdiction is a registration."
        ),
        "evidence_url": GIS_FAQ,
        "effective_from": PDQ_EFFECTIVE_FROM,
    },
    {
        "rule_id": "cr_tx_well_status_archive_1",
        "source_id": "tx_w10_wlf607",
        # The stage cr_tx_mft_resolve_1 already files an acquisition decision under: the
        # vocabulary admits no raw stage, and the choice of artifact is what the parse reads.
        "stage": "parse",
        "rule_kind": "parse_directive",
        "applies_to_fields": ["all"],
        "spec": {
            "archives": {
                "tx_w10_wlf607": {"link": W10_LINK, "names": ["wlf607.ebc", "wlf607.ebc.gz"]},
                "tx_g10_gse10": {"link": G10_LINK, "names": ["gse10.ebc", "gse10.ebc.gz"]},
            },
            "sibling_preference": "newest_modified",
            "parse": False,
            "module_function": "glasswell.ingest.tx_pdq:archive_well_status",
        },
        "rule": (
            "The two well-status files are archived monthly and parsed by nothing. Where a"
            " listing offers a compressed and an uncompressed twin, the vintage is the sibling"
            " the portal modified most recently, and which one was taken is recorded on the"
            " manifest."
        ),
        "rationale": (
            "The files hold the most recent 26-month reporting period against 402 months of"
            " PDQ history, so a window not archived monthly cannot be reconstructed from any"
            " regulator and allocation v1's test-rate weighting becomes impossible. They are"
            " archived and not parsed because v0 weights nothing by them."
            " The sibling preference is measured, not assumed, and it runs both ways: on"
            " 2026-09-03 the W-10 listing offered wlf607.ebc modified 2021-09-24 beside"
            " wlf607.ebc.gz modified 2026-08-25, while the G-10 listing offered gse10.ebc"
            " modified 2026-08-25 beside gse10.ebc.gz modified 2021-12-09. A fetcher that"
            " preferred either extension would take a five-year-old vintage for one of the two"
            " and never say so, so the rule is the modification date and the chosen name is"
            " recorded."
        ),
        "evidence_url": DOWNLOADS_PAGE,
        "effective_from": PDQ_EFFECTIVE_FROM,
    },
)

# Jurisdiction-neutral by id and Montana by source, the shape cr_mt_pru_reconciliation_1
# already has: a rule row cannot be sourceless (005_conformance.sql:7) and the study's evidence
# is Montana's files. Seeded separately because its source is registered by seed_sources, which
# runs after this module's seeder.
ALLOCATION_RULES: tuple[dict[str, object], ...] = (
    {
        "rule_id": "cr_alloc_v0_error_bounds_1",
        "source_id": "mt_bogc_pru_production",
        "stage": "validate",
        "rule_kind": "code_ref",
        "applies_to_fields": ["volume", "error_bounds"],
        "spec": {
            "model_id": ALLOCATION_MODEL_ID,
            "bed_jurisdiction": "MT",
            "bed_entity_predicate": "entity_type='well'",
            "statistic": "(allocated - truth) / (allocated + truth)",
            "statistic_range": [-1, 1],
            "excluded": "lease-months where both sides are zero, with the share served",
            "module_function": "glasswell.allocation.v0:symmetric_error",
            "transfer_outcome": "not_measured",
            "precondition_rule": "cr_mt_pru_reconciliation_1",
        },
        "rule": (
            "The equal-share method's error is measured against Montana, which files both"
            " well-level and lease-level volumes, over entity_type='well' rows regardless of"
            " reporting_level. The statistic is symmetric and bounded on [-1, 1]; lease-months"
            " where both sides are zero are excluded and the excluded share is served. Until"
            " the study is measured over a horizon shown to overlap Texas's, no band reaches a"
            " Texas figure and every allocated point carries outcome not_measured naming this"
            " rule."
        ),
        "rationale": (
            "A relative error is unbounded above and undefined where a well produced nothing in"
            " a month it was eligible for, which is the commonest case rather than an edge, so"
            " the symmetric measure is used instead. Montana writes three shapes for one"
            " well-month - per-pool rows, a well row aggregating them, and a well row where the"
            " filings are not decomposable - and summing the pool rows and the aggregate would"
            " double-count every decomposable well, so the bed is the well family and that is a"
            " mapping decision rather than a query. cr_mt_pru_reconciliation_1 measures that"
            " summing up agrees; it does not measure the error of splitting down, so it is"
            " cited as the precondition and never as the measurement. A band measured on"
            " another regulator's leases over a horizon that has not been shown to match is a"
            " naked number with a decoration."
        ),
        "evidence_url": PDQ_MANUAL,
        "effective_from": PDQ_EFFECTIVE_FROM,
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


def _rule_payload(rules: tuple[dict[str, object], ...]) -> list[dict[str, object]]:
    return [
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
        for rule in rules
    ]


def seed_conformance_tx(connection: psycopg.Connection) -> int:
    seed_sources_tx(connection)
    with connection.cursor() as cursor:
        cursor.executemany(_INSERT_RULE, _rule_payload(TX_RULES))
        cursor.execute(
            "select count(*) from lineage.conformance_rules where rule_id like 'cr_tx_%'"
        )
        return int(cursor.fetchone()[0])


def seed_conformance_allocation(connection: psycopg.Connection) -> int:
    """The method-study rule, whose source is Montana's and whose id belongs to no state."""
    with connection.cursor() as cursor:
        cursor.executemany(_INSERT_RULE, _rule_payload(ALLOCATION_RULES))
        cursor.execute(
            "select count(*) from lineage.conformance_rules where rule_id = any(%s)",
            ([str(rule["rule_id"]) for rule in ALLOCATION_RULES],),
        )
        return int(cursor.fetchone()[0])
