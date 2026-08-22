"""The ND conformance registry (SB-07 §6.2). Every rule is evidenced from a file we opened."""

from __future__ import annotations

from datetime import date

import psycopg
from psycopg.types.json import Jsonb

MPR_INDEX_URL = "https://www.dmr.nd.gov/oilgas/mprindex.asp"
MPR_FILE_URL = "https://www.dmr.nd.gov/oilgas/mpr/2026_03.xlsx"
GIS_WELLS_URL = "https://gis.dmr.nd.gov/downloads/oilgas/shapefile/OGD_Wells.zip"
GIS_LATERALS_URL = "https://gis.dmr.nd.gov/downloads/oilgas/shapefile/OGD_Horizontals_Line.zip"
GIS_SURVEYS_URL = "https://gis.dmr.nd.gov/downloads/oilgas/shapefile/OGD_Directionals.zip"

EFFECTIVE_FROM = date(2026, 1, 1)
# A superseding row carries the date its evidence was established, never the seed epoch.
SUPERSESSION_FROM = date(2026, 8, 20)
# M1-5's evidence date: the day OGD_Directionals.zip was fetched and its 52,579 stations,
# 525 wells and 586 segments were counted.
SURVEYS_FROM = date(2026, 8, 21)
# M1-7's decision date; the distribution it cites was verified against the FeatureServer.
DISPOSAL_FROM = date(2026, 8, 22)
# M1-3's decision date: geometry provenance became a served wire field on every ND layer.
PROVENANCE_FROM = date(2026, 8, 22)
GIS_WELLS_FEATURESERVER_URL = (
    "https://gis.dmr.nd.gov/dmrpublicservices/rest/services/"
    "OilGasPublicMapDataVectorTiles/Wells/FeatureServer/0"
)

# Per field, because the reject is the value and the ledger has to name which one broke.
SURVEY_STATION_BOUNDS: tuple[dict[str, object], ...] = (
    {"field": "inclination_deg", "min": 0, "max": 180, "unit": "deg"},
    {"field": "azimuth_deg", "min": 0, "max": 360, "unit": "deg"},
    {"field": "true_vertical_depth_ft", "max_field": "measured_depth_ft", "unit": "ft"},
)


def _bounds_predicate(bounds: tuple[dict[str, object], ...]) -> dict[str, object]:
    """The row-level form of the same bounds, generated so the two cannot drift apart.

    A null is admissible in both forms: an absent measurement is not an out-of-range one, and
    `_validity_filter` reads a null comparison as a failure unless the AST says otherwise.
    """
    clauses: list[dict[str, object]] = []
    for bound in bounds:
        column = {"col": bound["field"]}
        tests: list[dict[str, object]] = []
        if "min" in bound:
            tests.append({"cmp": [column, ">=", {"lit": bound["min"]}]})
        if "max" in bound:
            tests.append({"cmp": [column, "<=", {"lit": bound["max"]}]})
        if "max_field" in bound:
            tests.append({"cmp": [column, "<=", {"col": bound["max_field"]}]})
        # The conjunction is inside the null branch, not beside it: a bound with both ends
        # spread across the `or` would admit anything above its floor.
        clauses.append({"or": [{"is_null": column}, {"and": tests}]})
    return {"and": clauses}

ND_RULES: tuple[dict[str, object], ...] = (
    {
        "rule_id": "cr_nd_mpr_format_1",
        "source_id": "nd_mpr_xlsx",
        "stage": "parse",
        "rule_kind": "parse_directive",
        "applies_to_fields": ["all"],
        "spec": {
            "format_pin": "xlsx",
            "sheet": "Oil",
            "sheet_selector": "by_name",
            "header_policy": "first_row",
            "encoding": "utf-8",
        },
        "rule": "Read the monthly report from the XLSX sheet named Oil, header on row one.",
        "rationale": (
            "NDIC's index states that a past XLSX will not match the PDF of the same month"
            " because of amendments, so the format is pinned per period and never mixed within"
            " a month. The workbook carries two sheets, Oil and SkimmedCrudeRecovery; the sheet"
            " is selected by name, never by index, because sheet order is not a contract."
        ),
        "evidence_url": MPR_INDEX_URL,
    },
    {
        "rule_id": "cr_nd_api_identity_1",
        "source_id": "nd_mpr_xlsx",
        "stage": "parse",
        "rule_kind": "parse_directive",
        "applies_to_fields": ["api_wellno"],
        "spec": {
            "source_field": "API_WELLNO",
            "digits": 14,
            "api10_slice": [0, 10],
            "api12_slice": [0, 12],
        },
        "rule": "API-10 is the first ten digits of API_WELLNO; FileNo is not the identity key.",
        "rationale": (
            "Answers the identity question blueprint §3.0.4 and DIR-9 flag as the P1 blocker."
            " The free MPR carries both API_WELLNO and FileNo, and API_WELLNO is API-14"
            " (33053039010000), so no file-number crosswalk gates the ND chain. PPDM defines"
            " digits 1-12 only; 13-14 are convention, which is why they are sliced off rather"
            " than trusted (§3.0.5)."
        ),
        "evidence_url": MPR_FILE_URL,
    },
    {
        "rule_id": "cr_nd_month_convention_1",
        "source_id": "nd_mpr_xlsx",
        "stage": "parse",
        "rule_kind": "parse_directive",
        "applies_to_fields": ["report_date"],
        "spec": {
            "encoding": "excel_serial",
            "epoch": "1899-12-30",
            "semantics": "production_month",
        },
        "rule": "ReportDate is an Excel serial naming the production month, not the vintage.",
        "rationale": (
            "ReportDate 46082 decodes to 2026-03-01 on the 1899-12-30 epoch. It is valid time,"
            " the month produced; knowledge time comes from the manifest's self-stamped"
            " fetch_vintage, never from the pipeline clock (DIR-2)."
        ),
        "evidence_url": MPR_FILE_URL,
    },
    {
        "rule_id": "cr_nd_land_unit_1",
        "source_id": "nd_mpr_xlsx",
        "stage": "parse",
        "rule_kind": "parse_directive",
        "applies_to_fields": ["township", "range", "section"],
        "spec": {
            "label_format": "{twp}N-{rng}W-{sec}",
            "note": "ND lies wholly north and west of the fifth principal meridian",
        },
        "rule": "Supply the N/W direction letters ND omits from township and range.",
        "rationale": (
            "The MPR ships bare Township 151 and Range 101 with no direction letters. North"
            " Dakota lies wholly north and west of the fifth principal meridian, so the letters"
            " are supplied by a rule that says so rather than hardcoded in a parser."
        ),
        "evidence_url": MPR_FILE_URL,
    },
    {
        "rule_id": "cr_nd_volume_range_1",
        "source_id": "nd_mpr_xlsx",
        "stage": "validate",
        "rule_kind": "validity_filter",
        "applies_to_fields": ["oil", "wtr", "gas"],
        "spec": {
            "predicate_ast": {
                "and": [
                    {"cmp": [{"col": "oil"}, ">=", {"lit": 0}]},
                    {"cmp": [{"col": "wtr"}, ">=", {"lit": 0}]},
                    {"cmp": [{"col": "gas"}, ">=", {"lit": 0}]},
                ]
            },
            "on_fail": "quarantine",
            "reason_code": "impossible_volume",
        },
        "rule": "A reported monthly volume is never negative.",
        "rationale": (
            "Negative volumes are physically impossible, so they are quarantined with a reason"
            " and never dropped. A zero quarantine rate is read as evidence that the checks are"
            " not running, which is the blueprint's own P1 exit criterion."
        ),
        "evidence_url": MPR_FILE_URL,
    },
    {
        "rule_id": "cr_nd_confidential_1",
        "effective_from": SUPERSESSION_FROM,
        "source_id": "nd_mpr_xlsx",
        "stage": "validate",
        "rule_kind": "validity_filter",
        "applies_to_fields": ["pool"],
        "spec": {
            "predicate_ast": {
                "or": [
                    {"is_null": {"col": "pool"}},
                    {"not": {"cmp": [{"col": "pool"}, "==", {"lit": "CONFIDENTIAL"}]}},
                ]
            },
            "on_fail": "quarantine",
            "reason_code": "confidential_withheld",
        },
        "rule": "A month NDIC pools as CONFIDENTIAL is withheld, not missing and not invalid.",
        "rationale": (
            "ND publishes a confidential well's month with the literal string NULL in Oil, Wtr,"
            " Gas and Days and Pool = CONFIDENTIAL. cr_nd_days_range_1 compiles to"
            " between(days, 0, 31), which cannot judge a row that has no days, so the row fell"
            " out under out_of_range_date - a code asserting that a value exists and is wrong,"
            " for a value the regulator withheld (fp-audit D2 / A5-F7, 1,055 well-months)."
            " This rule runs first, by rule_id order, and gives the withholding its own name."
            " Confidential is a status, and withheld is a distinct state from missing (§3.0.3)."
        ),
        "evidence_url": MPR_FILE_URL,
    },
    {
        "rule_id": "cr_nd_days_range_1",
        "source_id": "nd_mpr_xlsx",
        "stage": "validate",
        "rule_kind": "validity_filter",
        "applies_to_fields": ["days"],
        "spec": {
            "predicate_ast": {"between": [{"col": "days"}, {"lit": 0}, {"lit": 31}]},
            "on_fail": "quarantine",
            "reason_code": "out_of_range_date",
        },
        "rule": "Days produced falls within a calendar month.",
        "rationale": (
            "Days is days-produced within the report month, so 0 to 31 inclusive is the whole"
            " admissible range. A row outside it has a parse or an amendment problem that a"
            " downstream rate calculation would otherwise absorb silently."
        ),
        "evidence_url": MPR_FILE_URL,
    },
    {
        "rule_id": "cr_nd_entity_key_1",
        "source_id": "nd_mpr_xlsx",
        "stage": "conform",
        "rule_kind": "key_composite",
        "applies_to_fields": ["api10", "pool"],
        "spec": {
            "source_cols": ["api10", "pool"],
            "separator": ":",
            "target_col": "entity_key",
            "on_missing": "passthrough",
            "uniqueness_scope": "api10",
        },
        "rule": "The pool entity key is the API-10 joined to the pool the operator filed under.",
        "rationale": (
            "The MPR's grain is (API-14, pool, month) while migration 008 keyed canonical on"
            " (api10, month, stream), so a well completed in two pools collided on real data and"
            " all but the first row by spreadsheet ordinal were quarantined (fp-audit D1: 78"
            " wells, 454 well-months, 139,644 bbl). The key is built from registry columns"
            " rather than a literal in the parser because the same executor builds NM's"
            " well-completion key and TX's (OIL_GAS_CODE, DISTRICT_NO, LEASE_NO) lease key"
            " (SB-01 §2.10, §4.1). A month NDIC filed with no pool label passes through unkeyed:"
            " it is an observation of the well, and inventing a pool for it would be a fact the"
            " source does not carry."
        ),
        "evidence_url": MPR_FILE_URL,
        "effective_from": SUPERSESSION_FROM,
    },
    {
        "rule_id": "cr_nd_pool_rollup_1",
        "source_id": "nd_mpr_xlsx",
        "stage": "conform",
        "rule_kind": "code_ref",
        "applies_to_fields": ["volume", "days_produced", "null_semantics"],
        "spec": {
            "module_function": "glasswell.ingest.nd_mpr:pool_promotion_records",
            "version": "1",
            "aggregation": "sum_over_pools",
            "volume": "exact sum over the pool filings of the well-month-stream",
            "days_produced": "maximum over the pool filings, never the sum",
            "null_semantics": "reported unless every pool filing is absent, then no_report",
            "contract_note": (
                "one filing promotes as the well; two or more promote as one row per pool plus a"
                " well row carrying their exact sum, disclosed as aggregation = sum_over_pools"
            ),
        },
        "code_ref": "glasswell.ingest.nd_mpr:pool_promotion_records",
        "rule": (
            "A well that filed in more than one pool is one row per pool plus a well total that"
            " says it is a sum."
        ),
        "rationale": (
            "Summing across pools is legislated here rather than performed at serve time: a"
            " serve-time sum is a figure with no derivation to cite, which R6 and R7 forbid, and"
            " it was why D1's interim fix withdrew the point instead. Volume sums exactly because"
            " the pool filings are disjoint observations of the same wellbore-month. Days do not"
            " sum - a well cannot produce more days than the month holds and the pool filings are"
            " concurrent, so the well's days are the maximum over its pools. The well row carries"
            " reporting_level = well_completion_pool and aggregation = sum_over_pools so the"
            " consumer can tell a two-pool well from a one-pool well, which S-B requires because"
            " they are different objects. A well-month with exactly one filing is promoted as the"
            " well directly: the sum over one pool is that pool, and relabelling 394,278"
            " unaffected rows as aggregates would signal a restatement that did not happen"
            " (DIR-2)."
        ),
        "evidence_url": MPR_FILE_URL,
        "effective_from": SUPERSESSION_FROM,
    },
    {
        "rule_id": "cr_nd_stream_vocab_1",
        "source_id": "nd_mpr_xlsx",
        "stage": "conform",
        "rule_kind": "vocab_map",
        "applies_to_fields": ["stream_raw"],
        "spec": {
            "mapping_table": "nd_stream_promoted_map",
            "key_col": "stream_raw",
            "value_col": "stream_canonical",
            "unmapped_action": "quarantine",
            "reason_code": "stream_not_promoted",
        },
        "rule": "Promote Oil, Wtr and Gas; quarantine every other reported column as a"
        " disposition.",
        "rationale": (
            "canonical.production_monthly admits oil, gas and water only. GasSold and Flared are"
            " dispositions of produced gas, not streams: they are recorded in nd_stream_map as"
            " not promoted and quarantine with a reason, so conflict C7's claim is measured"
            " rather than asserted. The rule reads the promoted view because the executor"
            " stringifies lookup values and a NULL would promote as the text 'None'."
        ),
        "evidence_url": MPR_FILE_URL,
    },
    {
        "rule_id": "cr_nd_units_1",
        "source_id": "nd_mpr_xlsx",
        "stage": "conform",
        "rule_kind": "unit_conform",
        "applies_to_fields": ["oil", "wtr", "gas"],
        "spec": {
            "units": {"oil": "bbl", "wtr": "bbl", "gas": "mcf"},
            "factor": "1",
            "rounding": "half_even",
            "scale": 3,
            "conditions_note": (
                "mcf at the regulator's stated conditions; conditions recorded, not normalized"
            ),
        },
        "rule": "ND reports oil and water in bbl and gas in mcf; no conversion, declared units.",
        "rationale": (
            "Blueprint §3.0.3's gas-conditions rule and the A-13 unit-declaration obligation:"
            " every numeric canonical field declares a unit. The factor is 1 because the"
            " reported units already are the canonical ones - the rule exists to record that,"
            " and to fix the rounding mode and scale rather than inherit the runtime's."
        ),
        "evidence_url": MPR_FILE_URL,
    },
    {
        "rule_id": "cr_nd_liquids_policy_1",
        "source_id": "nd_mpr_xlsx",
        "stage": "conform",
        "rule_kind": "code_ref",
        "applies_to_fields": ["oil"],
        "spec": {
            "module_function": "glasswell.ingest.nd_mpr:liquids_basis",
            "version": "1",
            "contract_note": (
                "returns the constant basis string 'oil+condensate' attached to every ND liquids"
                " figure"
            ),
        },
        "code_ref": "glasswell.ingest.nd_mpr:liquids_basis",
        "rule": "ND liquids are oil plus condensate; the basis travels with every liquids figure.",
        "rationale": (
            "A policy statement, not a mapping, so it is recorded as the kind SB-07 §6.1"
            " provides for exactly that. The code_ref executor is unimplemented in this slice:"
            " the promotion path filters code_ref rows out of apply_rules and reads"
            " spec.contract_note for the basis. Recorded as a known limitation."
        ),
        "evidence_url": MPR_INDEX_URL,
    },
    {
        "rule_id": "cr_nd_null_semantics_1",
        "source_id": "nd_mpr_xlsx",
        "stage": "conform",
        "rule_kind": "code_ref",
        "applies_to_fields": ["null_semantics"],
        "spec": {
            "module_function": "glasswell.ingest.nd_mpr:classify_null_semantics",
            "version": "1",
            "contract_note": (
                "labels each row reported / reported_zero / no_report / withheld; never removes"
                " a row"
            ),
        },
        "code_ref": "glasswell.ingest.nd_mpr:classify_null_semantics",
        "rule": "Classify why a volume is absent; never delete the row that carries the absence.",
        "rationale": (
            "No report filed, reported zero and withheld as confidential are three different"
            " facts and are never collapsed (§3.0.3). A filter would delete a confidential"
            " well's withheld month outright, destroying the distinction it claims to preserve,"
            " so this is a classifier writing canonical.production_monthly.null_semantics."
        ),
        "evidence_url": MPR_FILE_URL,
    },
    {
        "rule_id": "cr_nd_status_vocab_1",
        "source_id": "nd_gis_wells",
        "stage": "conform",
        "rule_kind": "vocab_map",
        "applies_to_fields": ["status"],
        "spec": {
            "mapping_table": "nd_status_map",
            "key_col": "status",
            "value_col": "status_canonical",
            "unmapped_action": "quarantine",
            "reason_code": "unknown_status",
        },
        "rule": "Map the NDIC well-status code to the canonical status vocabulary.",
        "rationale": (
            "Measured from OGD_Wells.dbf (43,812 records): A 20640, PA 6447, DRY 6347, PNC 5725,"
            " IA 1597, Confidential 962, AB 842, LOC 610, DRL 340, TA 174, TAO 30, PANF 27,"
            " EXP 22, PNS 20, TASC 11, TATD 8, NC 7, LOCR 2, NJ 1. The canonical set is active,"
            " plugged, dry, permitted, inactive, confidential, drilling, temporarily_abandoned"
            " and expired; the permit-lifecycle terminal codes collapse to expired. Confidential"
            " is a status, which is why the well record carries a confidential flag and why"
            " withheld is a distinct state from missing (§3.0.3)."
        ),
        "evidence_url": GIS_WELLS_URL,
    },
    {
        "rule_id": "cr_nd_datum_1",
        "source_id": "nd_gis_wells",
        "stage": "conform",
        "rule_kind": "datum_transform",
        "applies_to_fields": ["latitude", "longitude", "geom"],
        "spec": {
            "source_epsg": 4269,
            "target_epsg": 4326,
            "detect": {"prj_contains": "GCS_North_American_1983"},
        },
        "rule": "Transform NAD83 well coordinates to EPSG:4326 before they reach storage.",
        "rationale": (
            "Read from the shipped .prj: GEOGCS[\"GCS_North_American_1983\",DATUM"
            "[\"D_North_American_1983\",...]], which is EPSG:4269. ND is NAD83, not NAD27 (that"
            " is the Texas hazard) and not literally WGS84. Storage is always 4326 and the"
            " transform is recorded as a derivation node even though the shift is sub-metre:"
            " the rule is that no coordinate reaches storage untransformed and unrecorded."
        ),
        "evidence_url": GIS_WELLS_URL,
    },
    {
        "rule_id": "cr_nd_compute_crs_1",
        "source_id": "nd_gis_horizontals_line",
        "stage": "conform",
        "rule_kind": "parse_directive",
        "applies_to_fields": ["geom"],
        "spec": {
            "storage_epsg": 4326,
            "compute_epsg": 32614,
            "purpose": "length_computation",
            "length_expression": "ST_Length(ST_Transform(geom, 32614))",
            "forbidden_field": "SHAPE_Leng",
        },
        "rule": "Compute lateral length in UTM 14N; never read the shapefile's own length field.",
        "rationale": (
            "OGD_Horizontals_Line.dbf ships SHAPE_Leng in degrees (1.51394994807e-02). Using it"
            " as a length is a defect, so length comes from ST_Length(ST_Transform(geom, 32614))"
            " (§3.0.3 compute-CRS rule). Recorded as a directive rather than a datum_transform"
            " because it configures a projected computation over a geometry column, and the"
            " datum executor moves x/y columns rather than geometry."
        ),
        "evidence_url": GIS_LATERALS_URL,
    },
    {
        "rule_id": "cr_nd_compute_crs_2",
        "supersedes_rule_id": "cr_nd_compute_crs_1",
        "effective_from": SUPERSESSION_FROM,
        "source_id": "nd_gis_horizontals_line",
        "stage": "conform",
        "rule_kind": "parse_directive",
        "applies_to_fields": ["geom"],
        "spec": {
            "storage_epsg": 4326,
            "length_method": "geodesic",
            "ellipsoid": "WGS84",
            "purpose": "length_computation",
            "length_expression": "ST_Length(geom::geography)",
            "forbidden_field": "SHAPE_Leng",
        },
        "rule": "Measure lateral length geodesically on the WGS84 ellipsoid; never project it"
        " into a UTM zone and never read the shapefile's own length field.",
        "rationale": (
            "Supersedes cr_nd_compute_crs_1 on the evidence in fp-audit A3-F1: 22,661 of 23,228"
            " ND laterals (97.6 percent) lie west of 102W, outside EPSG:32614's band, which"
            " overstated the fleet by 144,378.78 ft (+0.0709 percent) and 3,030 laterals by more"
            " than ten feet. The Williston basin spans UTM 13N and 14N, so a basin-keyed compute"
            " CRS cannot be correct for both halves of it and the schema cannot express the right"
            " answer. A geodesic length chooses no zone. Measured against an independent pyproj"
            " Geod(ellps=WGS84) traverse over a 100-lateral sample spanning 104.01W to 100.97W,"
            " ST_Length(geom::geography) agrees to 2.4e-8 m (8e-8 ft, 1.1e-7 percent), while the"
            " superseded EPSG:32614 differs by up to 6.632 ft (0.145 percent) and the best"
            " projected alternative - per-feature UTM zone chosen by centroid longitude - by up"
            " to 1.460 ft (0.033 percent). SHAPE_Leng stays forbidden for the reason"
            " cr_nd_compute_crs_1 gave: it is published in degrees."
        ),
        "evidence_url": GIS_LATERALS_URL,
    },
    {
        "rule_id": "cr_nd_segment_vocab_1",
        "effective_from": SUPERSESSION_FROM,
        "source_id": "nd_gis_horizontals_line",
        "stage": "conform",
        "rule_kind": "vocab_map",
        "applies_to_fields": ["segment"],
        "spec": {
            "mapping_table": "nd_segment_promoted_map",
            "key_col": "segment",
            "value_col": "geom_type",
            "unmapped_action": "quarantine",
            "reason_code": "segment_not_promoted",
        },
        "rule": "Promote the LAT centreline; hold the vertical hole and the sidetrack as a"
        " disposition.",
        "rationale": (
            "OGD_Horizontals_Line ships three segment kinds in linekey: LAT (23,234 rows), VERT"
            " (21,302) and STK (4,147). Only the lateral is a producing centreline, so promoting"
            " a vertical segment as one would be wrong - but the other two are not unknown"
            " vocabulary, which is what the loader's literal made the ledger say for 24,872 rows"
            " whose own payload carried the segment the loader had parsed (fp-audit A5-F6). The"
            " choice is a vocabulary, so it is a table, and the rows it holds back say what they"
            " are. 68 wells have a sidetrack and no lateral; their card discloses the held-back"
            " trace rather than reading as a well with no horizontal at all (fp-audit A3-F3)."
        ),
        "evidence_url": GIS_LATERALS_URL,
    },
    {
        "rule_id": "cr_nd_multilateral_1",
        "source_id": "nd_gis_horizontals_line",
        "stage": "validate",
        "rule_kind": "validity_filter",
        "applies_to_fields": ["linekey", "lateral_ordinal"],
        "spec": {
            "predicate_ast": {"cmp": [{"col": "lateral_ordinal"}, "<=", {"lit": 1}]},
            "on_fail": "quarantine",
            "reason_code": "multi_wellbore_policy",
            "disposition": "measure_only",
            "ordinal_source": "the _LAT<n> suffix of linekey",
        },
        "rule": "Measure how often one API-10 carries more than one lateral centreline.",
        "rationale": (
            "linekey is <API14>_LAT<n> and 48,688 line records map to 43,812 wells, so"
            " multi-lateral wells are real and common. Per conflict C10 every geometry still"
            " loads: the quarantine batch measures the §3.0.5 rate against the 2 percent ND"
            " trigger rather than rejecting data, which is why the spec is marked measure_only."
        ),
        "evidence_url": GIS_LATERALS_URL,
    },
    {
        "rule_id": "cr_nd_survey_api_identity_1",
        "effective_from": SURVEYS_FROM,
        "source_id": "nd_gis_directionals",
        "stage": "parse",
        "rule_kind": "parse_directive",
        "applies_to_fields": ["api_wellno"],
        "spec": {
            "source_field": "api_wellno",
            "digits": 14,
            "api10_slice": [0, 10],
            "trailing_unused_slice": [10, 14],
            "on_short_value": "quarantine",
            "reason_code": "key_incomplete",
        },
        "rule": "API-10 is the first ten digits of api_wellno; the trailing four are dropped.",
        "rationale": (
            "cr_nd_api_identity_1 makes the same slice on the MPR and rests on the PPDM"
            " observation that digits 13-14 are convention. This layer supplies the regulator's"
            " own statement of it: the attribute definition for api_wellno in"
            " OGD_Directionals.shp.xml reads verbatim \"First 2 numbers are State ID, next 3"
            " numbers are County ID, next 4 numbers are Unique Index Number, last 4 numbers are"
            " not used by the State of North Dakota\". All 52,579 station records carry 14"
            " digits and every one of them ends 0000, so the drop discards nothing ND uses. A"
            " row whose api_wellno is not 14 digits has no identity to promote and quarantines"
            " as key_incomplete rather than being keyed on a guess."
        ),
        "evidence_url": GIS_SURVEYS_URL,
    },
    {
        "rule_id": "cr_nd_survey_segment_vocab_1",
        "effective_from": SURVEYS_FROM,
        "source_id": "nd_gis_directionals",
        "stage": "conform",
        "rule_kind": "vocab_map",
        "applies_to_fields": ["well_sub"],
        "spec": {
            "mapping_table": "nd_survey_segment_promoted_map",
            "key_col": "well_sub",
            "value_col": "segment_kind",
            "unmapped_action": "quarantine",
            "reason_code": "segment_not_promoted",
        },
        "rule": "Every known well_sub is a surveyed bore segment and every one is promoted; an"
        " unlisted label is held back as a disposition rather than traced.",
        "rationale": (
            "ND's own attribute definition for well_sub reads \"categorized well bore portions"
            " are assigned a description as Lateral (LAT), Vertical (VERT), or Sidetrack (STK)\","
            " and the layer then ships DIR for 40,138 of 52,579 stations - a value the"
            " publisher's metadata does not list, explained by this layer's abstract, \"deviated"
            " well bore but not at the severity of a horizontal\". Measured vocabulary: DIR"
            " 40,138, VERT 10,648, STK1 1,522, STK2 221, STK3 38, STK4 12. Unlike"
            " cr_nd_segment_vocab_1, which promotes only the producing centreline, every"
            " segment here is promoted: the whole point of a survey trace is the path the hole"
            " actually took, and a vertical hole has one. LAT is seeded with no station behind"
            " it because ND documents the value; a vocabulary seeded only from one file's"
            " contents quarantines every row on the day the publisher uses it."
        ),
        "evidence_url": GIS_SURVEYS_URL,
    },
    {
        "rule_id": "cr_nd_survey_station_order_1",
        "effective_from": SURVEYS_FROM,
        "source_id": "nd_gis_directionals",
        "stage": "conform",
        "rule_kind": "parse_directive",
        "applies_to_fields": ["measdpth", "geom"],
        "spec": {
            "source_field": "measdpth",
            "order_by": "measured_depth_ft",
            "direction": "ascending",
            "tie_break": "source_row_ordinal",
            "assembly": "linestring_through_stations",
            "ordinal_from": 0,
            "on_missing_order_key": "quarantine",
            "reason_code": "unreliable_numeric",
        },
        "rule": "Assemble the trace by joining the stations of one segment in ascending measured"
        " depth, breaking ties on source row order.",
        "rationale": (
            "The layer ships no station sequence column, so the order the vertices are joined in"
            " is a decision and not a reading. Measured depth is the only monotone quantity a"
            " survey has: TVD is not monotone in a horizontal and the coordinate offsets are"
            " not ordered at all. The file happens to arrive in that order already for all 586"
            " segments, which is why the sort is stated rather than assumed - a future vintage"
            " that arrives unsorted must produce the same trace. Two segments carry a repeated"
            " measured depth (33007016430000 VERT at 2050 ft, 33053026840000 VERT at 6945 ft),"
            " so the tie-break is named: without it those two traces would depend on Postgres"
            " row order and the artifact would not be D1-reproducible. A station with no"
            " measured depth has no place in the order at all - parking it at whichever end a"
            " null sorts to would put a vertex somewhere the source did not - so it is"
            " quarantined as unreliable_numeric instead of being ordered on a guess. No station"
            " in the measured vintage is missing one."
        ),
        "evidence_url": GIS_SURVEYS_URL,
    },
    {
        "rule_id": "cr_nd_survey_station_range_1",
        "effective_from": SURVEYS_FROM,
        "source_id": "nd_gis_directionals",
        "stage": "validate",
        "rule_kind": "validity_filter",
        "applies_to_fields": ["inclination_deg", "azimuth_deg", "true_vertical_depth_ft"],
        "spec": {
            "bounds": list(SURVEY_STATION_BOUNDS),
            "predicate_ast": _bounds_predicate(SURVEY_STATION_BOUNDS),
            "on_fail": "quarantine",
            "field_action": "null_field",
            "reason_code": "unreliable_numeric",
            "disposition": "measure_only",
        },
        "rule": "A measurement outside its physical range is withheld from the station row and"
        " recorded as a rejected value; the station's own position still promotes.",
        "rationale": (
            "Seven values in 52,579 stations cannot be true: inclination 436 deg at"
            " 33007003310000 STK1, azimuth 437 deg at 33075014950000 DIR, and five stations"
            " whose TVD exceeds their own measured depth by up to 0.77 ft. The reject is the"
            " value, not the row: ND computed the published long/lat itself and a defective"
            " azimuth is no evidence against the coordinate beside it. Dropping the station"
            " would have truncated two traces at an end - the 33075014950000 defect is on the"
            " deepest of its 150 stations - which is the honesty gap this layer exists to close."
            " So the field is nulled, the station promotes, and one quarantine row per rejected"
            " value carries the number and the bound it broke. Marked measure_only for the"
            " reason cr_nd_multilateral_1 is: the batch is a measurement, not a rejection of"
            " data, and no geometry is lost to it. field_action and disposition are read by the"
            " loader rather than described by it - flipping field_action to drop_row in this row"
            " changes what the promotion does, and both values are stamped on every reject so"
            " the ledger can tell a withheld value from a lost row without joining back here."
            " The spec carries the same bounds twice on"
            " purpose - predicate_ast is the row-level form every validity_filter executor"
            " runs, bounds is the per-field breakdown that lets the ledger name the column -"
            " and the AST is generated from the bounds list so the two cannot drift."
        ),
        "evidence_url": GIS_SURVEYS_URL,
    },
    {
        "rule_id": "cr_nd_survey_min_stations_1",
        "effective_from": SURVEYS_FROM,
        "source_id": "nd_gis_directionals",
        "stage": "validate",
        "rule_kind": "validity_filter",
        "applies_to_fields": ["station_count"],
        "spec": {
            "predicate_ast": {"cmp": [{"col": "station_count"}, ">=", {"lit": 2}]},
            "min_stations": 2,
            "on_fail": "quarantine",
            "reason_code": "insufficient_stations",
        },
        "rule": "A segment needs two stations before it is a trace; its stations still promote.",
        "rationale": (
            "A LineString needs two vertices. The shallowest segment in the measured vintage is"
            " 33075011520000 DIR with exactly two, so no segment is held back today - but a"
            " single-station segment is a shape the source can file and the alternative to this"
            " rule is a trace that silently does not appear. The stations are promoted either"
            " way: what is quarantined is the trace that could not be drawn, which is why the"
            " payload is the segment and not a station row."
        ),
        "evidence_url": GIS_SURVEYS_URL,
    },
    {
        "rule_id": "cr_nd_survey_azimuth_reference_1",
        "effective_from": SURVEYS_FROM,
        "source_id": "nd_gis_directionals",
        "stage": "conform",
        "rule_kind": "parse_directive",
        "applies_to_fields": ["azimuth"],
        "spec": {
            "north_reference": "unstated_by_publisher",
            "conversion": "none",
            "canonical_column": "azimuth_deg",
            "served_as": "reported",
        },
        "rule": "Serve azimuth exactly as ND filed it; state that the north reference is"
        " unpublished rather than assume true, grid or magnetic north.",
        "rationale": (
            "OGD_Directionals.shp.xml carries an attribute definition for api_wellno, well_sub,"
            " measdpth, tvd and wl_permit and none at all for azimuth, inclinatio, coordns or"
            " coordew. A survey azimuth is meaningless without its north reference, and true,"
            " grid and magnetic north differ by degrees in the Williston basin, so converting"
            " under an assumed reference would put a fabricated number into a column a reader"
            " treats as a measurement. The honest form is the filed number plus this row saying"
            " what is not known about it, which is what ?explain resolves. Also the reason the"
            " canonical column is a plan-view coordinate and not a computed minimum-curvature"
            " position: recomputing station positions from MD/INC/AZI needs the reference this"
            " rule records as missing, and ND already published the positions."
        ),
        "evidence_url": GIS_SURVEYS_URL,
    },
    {
        "rule_id": "cr_nd_well_type_disposal_1",
        "effective_from": DISPOSAL_FROM,
        "source_id": "nd_gis_wells",
        "stage": "conform",
        "rule_kind": "code_ref",
        "applies_to_fields": ["well_type"],
        "spec": {
            "module_function": "glasswell.marts.tiles:ND_LAYERS",
            "version": "1",
            "classification": "disposal_injection",
            "well_type_codes": ["SWD", "WI", "CO2I", "AI", "GI", "SFI", "MWUI", "INJP"],
            "code_semantics": "verbatim NDIC well_type codes; no per-code decode is asserted",
            "contract_note": "the map's disposal-wells layer draws exactly these eight codes"
            " as a ring; the attribute reaches the tile verbatim from"
            " canonical.wells.well_type_reported (web/src/map/disposal.ts is the filter)",
        },
        "rule": "Class a well as disposal/injection where NDIC's well_type code is SWD, WI,"
        " CO2I, AI, GI, SFI, MWUI or INJP.",
        "rationale": (
            "Measured by groupBy on the NDIC Wells FeatureServer (43,824 wells): OG 40,180,"
            " SWD 1,059, Confidential 964, WI 848, GASD 279, ST 183, GASC 106, WS 95, CO2I 43,"
            " AI 22, GI 10, SFI 4, MWUI 2, INJP 1. The eight listed codes are the injection"
            " class the survey verified, 1,989 wells; the excluded codes are not asserted to"
            " be injection wells by any NDIC statement held here. The SWD / EXP-SWD / PANF-SWD"
            " labels on NDIC's own vector tiles are status-type composites, not distinct types"
            " — status independently carries EXP (18) and PANF (27) — so the class is keyed to"
            " well_type alone. The codes are drawn verbatim; which words each abbreviates is"
            " the regulator's decoder to own, and this rule asserts no decode."
        ),
        "evidence_url": GIS_WELLS_FEATURESERVER_URL,
        "code_ref": "web/src/map/disposal.ts",
    },
    {
        "rule_id": "cr_nd_geometry_provenance_1",
        "effective_from": PROVENANCE_FROM,
        "source_id": "nd_gis_wells",
        "stage": "conform",
        "rule_kind": "code_ref",
        "applies_to_fields": ["geom"],
        "spec": {
            "module_function": "glasswell.marts.nd_wells:_PROJECTIONS",
            "version": "1",
            "classification": "geometry_provenance",
            "classes": {
                "surface": "reported wellhead point from OGD_Wells.zip",
                "lateral": "filed horizontal centreline from OGD_Horizontals_Line.zip —"
                " not a directional survey trace",
                "survey_trace": "plan-view path assembled from OGD_Directionals.zip"
                " MD/INC/AZI/TVD stations",
            },
            "code_semantics": "verbatim canonical geom_type values; served unchanged as"
            " geometry_provenance on every ND tile layer, no per-class decode beyond this map",
            "tx_exclusion": "TX RRC publishes GIS_LOCATION_SOURCE (data-sources-wellops.md"
            " §6.2) but the field is RRC content and sits under the RF-1 licence question"
            " (data-sources-infra.md §10); the TX half of M1-3 is not served until RF-1 is"
            " answered",
            "contract_note": "the nd_wells, nd_laterals and nd_survey_traces tiles each carry"
            " geometry_provenance verbatim from canonical.well_spatial.geom_type; each layer"
            " is homogeneous in it, so the layer toggles are the provenance filter and the"
            " per-layer paints are the style channel (web/src/map/provenance.ts is the"
            " consumer)",
        },
        "rule": "Serve canonical.well_spatial.geom_type verbatim as geometry_provenance on"
        " every ND tile layer: surface, lateral or survey_trace.",
        "rationale": (
            "Each ND geometry family's coordinates come from a distinct DMR filing: OGD_Wells"
            " publishes the reported wellhead point, OGD_Horizontals_Line the filed centreline"
            " (explicitly not a survey — its linekeys are LAT/STK/VERT segments), and"
            " OGD_Directionals the survey stations a trace is assembled from. Mapping each"
            " filing to one geom_type class at ingest is the provenance decision, and serving"
            " the class verbatim gives the laterals row's hand-written caveat (\"not a"
            " directional survey trace\") a machine-readable backing. The classes are"
            " homogeneous within each layer, so no within-layer filter is asserted: the layer"
            " toggle is the filter. TX is excluded on licence, not on reach — see"
            " spec.tx_exclusion."
        ),
        "evidence_url": GIS_WELLS_URL,
        "code_ref": "web/src/map/provenance.ts",
    },
)

_INSERT = """
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
        "supersedes_rule_id": rule.get("supersedes_rule_id"),
        "effective_from": rule.get("effective_from", EFFECTIVE_FROM),
    }


def seed_conformance_nd(connection: psycopg.Connection) -> int:
    """Rule ids are immutable: a change is a new row with supersedes_rule_id (SB-07 §6.2)."""
    with connection.cursor() as cursor:
        cursor.executemany(_INSERT, [_row(rule) for rule in ND_RULES])
        # Counted per jurisdiction, not registry-wide: a second state's rows would otherwise
        # make this number depend on what else seed_all had already run.
        cursor.execute(
            "select count(*) from lineage.conformance_rules where source_id like 'nd\\_%%'"
        )
        return int(cursor.fetchone()[0])
