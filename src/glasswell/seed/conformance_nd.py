"""The ND conformance registry (SB-07 §6.2). Every rule is evidenced from a file we opened."""

from __future__ import annotations

from datetime import date

import psycopg
from psycopg.types.json import Jsonb

MPR_INDEX_URL = "https://www.dmr.nd.gov/oilgas/mprindex.asp"
MPR_FILE_URL = "https://www.dmr.nd.gov/oilgas/mpr/2026_03.xlsx"
GIS_WELLS_URL = "https://gis.dmr.nd.gov/downloads/oilgas/shapefile/OGD_Wells.zip"
GIS_LATERALS_URL = "https://gis.dmr.nd.gov/downloads/oilgas/shapefile/OGD_Horizontals_Line.zip"

EFFECTIVE_FROM = date(2026, 1, 1)
# A superseding row carries the date its evidence was established, never the seed epoch.
SUPERSESSION_FROM = date(2026, 8, 20)

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
        cursor.execute("select count(*) from lineage.conformance_rules")
        return int(cursor.fetchone()[0])
