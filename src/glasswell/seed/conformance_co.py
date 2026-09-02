"""Colorado ECMC conformance rules: every mapping decision the fifth registration rests on (R8).

Colorado arrives as rows. The prefix, the status codebook, the location-qualifier axis, the
production grain and the rollup semantics are all decisions with a rationale and an effective
date here, so `ingest/co_*.py` reads them and writes none of them down. No state code appears
in any Colorado module; it lives in `cr_co_wells_api10_1`'s `spec.state_code` and nowhere else.

Every figure below was measured against the live ECMC files on 2026-09-02 -- the 124,410-record
header shapefile, the two 39,049-record directional archives and the 387,813-row rolling
production CSV -- and each byte count matches the `content-length` the host served.
"""

from __future__ import annotations

from datetime import date

import psycopg
from psycopg.types.json import Jsonb

# Valid time: the vintage of the archives these decisions describe. The three GIS archives
# carry last-modified 2026-09-01 and the header .dbf is stamped 2026-08-31.
EFFECTIVE_FROM = date(2026, 9, 1)

DOWNLOAD_ROOT = "https://ecmc.state.co.us/documents/data/downloads"
WELLS_SHP_URL = f"{DOWNLOAD_ROOT}/gis/WELLS_SHP.ZIP"
DIRECTIONAL_BH_URL = f"{DOWNLOAD_ROOT}/gis/DIRECTIONAL_BOTTOMHOLE_LOCATIONS_SHP.ZIP"
DIRECTIONAL_LINES_URL = f"{DOWNLOAD_ROOT}/gis/DIRECTIONAL_LINES_SHP.ZIP"
WELLS_METADATA_URL = f"{DOWNLOAD_ROOT}/gis/metadata/Wells_Metadata.html"
MONTHLY_PROD_URL = f"{DOWNLOAD_ROOT}/production/monthly_prod.csv"
PROD_REPORTS_URL = f"{DOWNLOAD_ROOT}/production/%s_prod_reports.csv"
PRODUCTION_DICTIONARY_URL = f"{DOWNLOAD_ROOT}/production/production_record_data_dictionary.htm"
STATUS_CODES_URL = "https://ecmc.state.co.us/cogisdb/statusCodes.html"
STATUS_CODES_PDF_URL = "https://ecmc.state.co.us/COGIS_Help/Status_Codes.pdf"
WELLS_REST_LAYER_URL = (
    "https://data.dnrgis.state.co.us/arcgis/rest/services/DNR_Public/OGCC_Wells/FeatureServer/0"
)

WELLS_SOURCE_ID = "co_ecmc_wells_shp"
BOTTOMHOLE_SOURCE_ID = "co_ecmc_directional_bh"
LINES_SOURCE_ID = "co_ecmc_directional_lines"
MONTHLY_SOURCE_ID = "co_ecmc_monthly_prod"
ARCHIVE_SOURCE_ID = "co_ecmc_prod_reports"

# The header shapefile, measured 2026-09-02: 124,410 features, 37 fields, one Facil_Type.
HEADER_FEATURES = 124410
HEADER_WELLS = 124392
EXACT_DUPLICATE_ROWS = 18
REST_LAYER_FEATURES = 123536

DOCUMENTED_UNMAPPED_CLASS = "documented_unmapped"

# Quoted verbatim from the live reference list (Last-Modified 2024-09-13), WELL STATUS CODES
# set. TA's words "COMPLETED WELL" carry the SO argument, so nothing here is abridged.
CO_STATUS_MAP: dict[str, dict[str, object]] = {
    "PA": {
        "decode": "PLUGGED AND ABANDONED WELL.",
        "status_canonical": "plugged",
        "wells": 55665,
    },
    "PR": {"decode": "PRODUCING WELL.", "status_canonical": "active", "wells": 35594},
    "AL": {
        "decode": "ABANDONED LOCATION: PERMIT VACATED; PER OPERATOR: WELL HAS NOT BEEN SPUD.",
        "status_canonical": "expired",
        "wells": 22422,
    },
    "SI": {
        "decode": "SHUT-IN WELL: COMPLETED WELL IS NOT PRODUCING BUT IS MECHANICALLY CAPABLE"
        " OF PRODUCTION.",
        "status_canonical": "inactive",
        "wells": 6541,
    },
    "TA": {
        "decode": "TEMPORARILY ABANDONED WELL: COMPLETED WELL NOT MECHANICALLY CAPABLE OF"
        " PRODUCTION WITHOUT INTERVENTION.",
        "status_canonical": "temporarily_abandoned",
        "wells": 1005,
    },
    "AP": {
        "decode": "ACTIVE PERMIT: APPROVED PERMIT TO DRILL WELL; NOT YET REPORTED AS SPUD.",
        "status_canonical": "permitted",
        "wells": 759,
    },
    "IJ": {
        "decode": "INJECTION WELL FOR WASTE DISPOSAL OR SECONDARY RECOVERY.",
        "status_canonical": "service",
        "wells": 686,
    },
    "EP": {
        "decode": "EXPIRED PERMIT: EXPIRED PERMIT TO DRILL WELL.",
        "status_canonical": "expired",
        "wells": 473,
    },
    "WO": {
        "decode": "WAITING ON COMPLETION: WELL HAS BEEN DRILLED BUT IS NOT YET REPORTED AS"
        " COMPLETED.",
        "status_canonical": "drilling",
        "wells": 409,
    },
    "AC": {
        "decode": "ACTIVE WELL: GAS STORAGE, OBSERVATION, OR DOMESTIC WELL.",
        "status_canonical": "service",
        "wells": 399,
    },
    "DG": {
        "decode": "DRILLING: WELL HAS SPUD BUT IS NOT REPORTED AS COMPLETED.",
        "status_canonical": "drilling",
        "wells": 304,
    },
    "SO": {
        "decode": "SUSPENDED OPERATIONS: DRILLING OPERATIONS SUSPENDED BEFORE REACHING PLANNED"
        " TOTAL DEPTH.",
        "status_canonical": DOCUMENTED_UNMAPPED_CLASS,
        "wells": 135,
    },
    "UN": {
        "decode": "UNKNOWN: OLD WELL WITH MINIMAL INFORMATION.",
        "status_canonical": DOCUMENTED_UNMAPPED_CLASS,
        "wells": 0,
    },
}

DOCUMENTED_WITHOUT_EQUIVALENT = tuple(
    code
    for code, row in CO_STATUS_MAP.items()
    if row["status_canonical"] == DOCUMENTED_UNMAPPED_CLASS
)
CLASSED_CODES = tuple(code for code in CO_STATUS_MAP if code not in DOCUMENTED_WITHOUT_EQUIVALENT)

# The two integers the layers panel serves, computed from the map rather than written down.
CLASSED_COUNT = len(CLASSED_CODES)
DOCUMENTED_COUNT = len(DOCUMENTED_WITHOUT_EQUIVALENT)

# All sixteen raw Loc_Qual strings, measured over the 124,392 deduplicated rows. They differ
# only in the case of the first token, which is why the rule case-folds it.
LOC_QUAL_DOMAIN: dict[str, int] = {
    "ACTUAL LatLong": 67920,
    "Planned Footage": 36150,
    "PLANNED LatLong": 18358,
    "Actual LatLong": 806,
    "PLANNED Footage": 608,
    "Planned LatLong": 448,
    "": 62,
    "ACTUAL GIS Online": 39,
    "PLANNED GIS Online": 4,
    "ACTUAL Footage": 4,
    "ECMC GIS Online": 3,
    "PLANNED QtrQtr": 3,
    "ECMC LatLong": 2,
    "Planned QtrQtr": 1,
    "ECMC Footage": 1,
    "Planned GIS Online": 1,
}
LOC_QUAL_CLASSES = {"actual": 68754, "planned": 55570, "ecmc": 6, "unstated": 62}
PLANNED_SHARE = "44.67%"
PLANNED_WITH_A_SPUD_DATE = 27976
PLANNED_ON_PLUGGED = 30369
PLANNED_ON_PRODUCING = 863

WELL_CLASS_DOMAIN: dict[str, int] = {
    "GW": 37002, "OW": 29939, "DA": 25396, "LO": 22971, "CBM": 5421, "": 1176, "ERI": 1112,
    "DSP": 607, "STO": 275, "OBW": 230, "CO2": 152, "DM": 48, "CLA": 32, "STR": 19, "HE": 18,
    "OTH": 10, "GEO": 2,
}

DIRECTIONAL_WELLBORES = 39049
DIRECTIONAL_WELLS = 37482
MULTI_WELLBORE_WELLS = DIRECTIONAL_WELLBORES - DIRECTIONAL_WELLS
MULTI_WELLBORE_SHARE = "4.18%"
DEVIATION_DOMAIN = {
    "Directional": 19524, "Horizontal": 15823, "Drifted": 3347, "": 336, "Vertical": 16,
    "High angle": 3,
}

# The rolling production file, measured end to end 2026-09-02.
PRODUCTION_ROWS = 387813
PRODUCTION_DISTINCT_KEYS = 387813
PRODUCTION_WELL_MONTHS = 339058
PRODUCTION_FOLDED_MONTHS = PRODUCTION_ROWS - PRODUCTION_WELL_MONTHS
PRODUCTION_DISTINCT_API10 = 44358
PRODUCTION_DENSE_MONTHS = 7
PRODUCTION_FIRST_MONTH = "2004-01"
PRODUCTION_LAST_MONTH = "2026-06"
PRODUCTION_DENSE_FIRST_MONTH = "2025-11"
PRODUCTION_DENSE_LAST_MONTH = "2026-05"
PRODUCTION_SIDETRACKS = {"00": 381094, "01": 6205, "02": 449, "04": 39, "03": 20, "05": 6}

# The sentence every Colorado cumulative is served beside. A total over a rolling window is
# honest only with its span stated, and this is the one place that sentence is written.
ROLLING_SPAN_NOTE = (
    "Cumulative over the months ECMC's rolling file carries, not over the well's life: the"
    " file's dense window is seven months and its late filings reach back sparsely, so a"
    " Colorado total is bounded by its own filings until the archive backfill dispatch."
)

CO_RULES: tuple[dict[str, object], ...] = (
    {
        "rule_id": "cr_co_wells_api10_1",
        "source_id": WELLS_SOURCE_ID,
        "stage": "conform",
        "rule_kind": "key_composite",
        "applies_to_fields": ["api_county", "api_seq", "api_label"],
        "spec": {
            "source_cols": ["api_county", "api_seq"],
            "pad": {"api_county": 3, "api_seq": 5},
            "pad_char": "0",
            "pad_side": "left",
            "separator": "",
            "target_col": "api10",
            "state_code": "05",
            "label_col": "api_label",
            "label_pattern": "^05-[0-9]{3}-[0-9]{5}$",
            "on_missing": "quarantine",
            "reason_code": "key_incomplete",
            "mirrors_rule_id": "cr_tx_api10_build_1",
            "measured": {
                "features": HEADER_FEATURES,
                "label_conforming": HEADER_FEATURES,
                "api_column_width": 8,
            },
        },
        "rule": (
            "A Colorado API-10 is the state code, the API_County padded to three and the"
            " API_Seq padded to five, concatenated as SSCCCUUUUU. A row whose API_Label does"
            " not match the labelled pattern is quarantined key_incomplete."
        ),
        "rationale": (
            "The header's own API column is eight characters, county plus sequence, and carries"
            " no state code at all: the state appears only inside API_Label, on all 124,410"
            " rows. So the API-10 is built rather than read, exactly as Texas builds one under"
            " cr_tx_api10_build_1, and the state code lives in this spec rather than in the"
            " parser. Measured over the whole file, 124,410 of 124,410 API_Labels match the"
            " pattern, so this rule raises no key_incomplete today; it is the guard for the day"
            " ECMC files one that does not."
        ),
        "evidence_url": WELLS_METADATA_URL,
        "code_ref": "src/glasswell/ingest/co_wells.py",
    },
    {
        "rule_id": "cr_co_wells_status_vocab_1",
        "source_id": WELLS_SOURCE_ID,
        "stage": "conform",
        "rule_kind": "vocab_map",
        "applies_to_fields": ["facil_stat"],
        "spec": {
            "canonical_mapping": {
                code: row["status_canonical"] for code, row in CO_STATUS_MAP.items()
            },
            "measured_wells": {code: row["wells"] for code, row in CO_STATUS_MAP.items()},
            "documented_without_equivalent": list(DOCUMENTED_WITHOUT_EQUIVALENT),
            "documented_without_equivalent_class": DOCUMENTED_UNMAPPED_CLASS,
            "unmapped_action": "passthrough",
            "resolved_at": "read_time",
            "writes_canonical_column": False,
            "resolver_view": "canonical.status_resolution",
            "mapping_table": "co_facility_status_map",
            "key_col": "status",
            "value_col": "status_canonical",
            "governing_set": "WELL STATUS CODES",
            "facility_type_measured": {"WELL": HEADER_FEATURES},
            "superseded_legends": {
                "shapefile_in_band": "Wells_Metadata.html, Metadata_Date 20151011, 16 codes,"
                " none of AP, EP or SO",
                "pdf": "Status_Codes.pdf, Rev 1-15-2017",
            },
        },
        "rule": (
            "ECMC's live Well Status reference list governs. Eleven codes map to a canonical"
            " class; SO and UN are documented and have no equivalent, so they resolve to"
            " documented_unmapped carrying the code the regulator filed. An unrecognised code"
            " passes through as unmapped rather than removing the well from the map."
        ),
        "rationale": (
            "Three legends disagree and the rule's job is to say which governs. The shapefile's"
            " own in-band legend lists sixteen codes and none of AP, EP or SO, and its"
            " Metadata_Date is 20151011; the 2017 PDF is superseded; the live reference list is"
            " the only one maintained after the COGCC to ECMC transition and the only one whose"
            " Well Status set covers every code in the data, so the 1,367 wells earlier research"
            " called unmappable are published after all. Facil_Type is WELL on all 124,410 rows,"
            " so the Well Status set governs rather than the wellbore, formation-completion or"
            " surface-location sets that share letters with different meanings. Three mappings"
            " carry the argument. AL is not an abandoned well: 22,422 rows are vacated permits"
            " where the operator states the well was never spud, which is expired's own"
            " definition, and classing them plugged would strike 22,422 wells through for a"
            " wellbore that does not exist. AC is not active: ECMC's text is gas storage,"
            " observation or domestic, which is service verbatim. SO has no counterpart:"
            " operations stopped before total depth, so the well is neither drilling"
            " (operations ceased), nor temporarily_abandoned (TA's own words require a completed"
            " well), nor dry (no determination was made). passthrough follows New Mexico rather"
            " than ND, TX and MT because the ECMC header is a single-file identity spine:"
            " quarantining on an unrecognised status would remove the well from the map"
            " entirely, and this vocabulary has changed twice in nine years. Read-time"
            " resolution is required rather than preferred: canonical.wells is append-only and"
            " ECMC refreshes daily, so writing the class at promotion would invent a valid time"
            " the regulator never filed."
        ),
        "evidence_url": STATUS_CODES_URL,
        "code_ref": "src/glasswell/ingest/co_wells.py",
    },
    {
        "rule_id": "cr_co_wells_dedup_1",
        "source_id": WELLS_SOURCE_ID,
        "stage": "validate",
        "rule_kind": "validity_filter",
        "applies_to_fields": ["api10", "facil_id", "loc_id", "facil_stat", "latitude",
                              "longitude"],
        "spec": {
            "keep": "min(ordinal)",
            "on_duplicate": "quarantine",
            "reason_code": "duplicate_row",
            "measured": {
                "features": HEADER_FEATURES,
                "distinct_api10": HEADER_WELLS,
                "byte_identical_extras": EXACT_DUPLICATE_ROWS,
                "extras_by_status": {"PR": 14, "SI": 4},
            },
        },
        "rule": (
            "Two feature rows that agree on every identifying attribute are one well. The row"
            " with the lowest source ordinal is kept and the discard is quarantined"
            " duplicate_row, never dropped."
        ),
        "rationale": (
            "124,410 features resolve to 124,392 distinct API-10. The eighteen extras are"
            " byte-identical feature rows -- same Facil_Id, Loc_ID, Facil_Stat and coordinates,"
            " fourteen PR and four SI -- not sidetracks and not distinct wells, so Colorado"
            " registers identity_is_unique true after this rule rather than joining the class"
            " of jurisdictions where API-10 is not a well key. Keeping the lowest ordinal is a"
            " decision and not an accident: the archive's order is the regulator's, and a"
            " rule that kept the last would make the promotion depend on how the file was"
            " walked."
        ),
        "evidence_url": WELLS_METADATA_URL,
        "code_ref": "src/glasswell/ingest/co_wells.py",
    },
    {
        "rule_id": "cr_co_wells_source_selection_1",
        "source_id": WELLS_SOURCE_ID,
        "stage": "join",
        "rule_kind": "code_ref",
        "applies_to_fields": ["all"],
        "spec": {
            "governing_source": WELLS_SOURCE_ID,
            "rejected_alternative": WELLS_REST_LAYER_URL,
            "measured": {
                "shapefile_features": HEADER_FEATURES,
                "rest_layer_features": REST_LAYER_FEATURES,
                "difference": HEADER_FEATURES - REST_LAYER_FEATURES,
            },
            "module_function": "glasswell.ingest.co_ecmc_gis:stage_layer",
            "contract_note": "The shapefile is the only header source staged or promoted.",
        },
        "rule": (
            "The ECMC shapefile governs the Colorado header, not the DNR ArcGIS feature layer."
        ),
        "rationale": (
            "The two sources disagree by 874 features, 124,410 against 123,536, and neither"
            " publishes an explanation of the difference. Choosing between them is a"
            " cross-source mapping decision, so it is a row. The shapefile wins because it"
            " carries its .prj in band, so the datum is declared rather than assumed, while the"
            " REST layer states its spatial reference only in the service's own response"
            " envelope. Registering the rejected alternative is what makes the choice"
            " reviewable when the counts converge or diverge further."
        ),
        "evidence_url": WELLS_SHP_URL,
        "code_ref": "src/glasswell/ingest/co_ecmc_gis.py",
    },
    {
        "rule_id": "cr_co_wells_datum_1",
        "source_id": WELLS_SOURCE_ID,
        "stage": "conform",
        "rule_kind": "datum_transform",
        "applies_to_fields": ["latitude", "longitude"],
        "spec": {
            "source_prj": "NAD_1983_UTM_Zone_13N",
            "resolved_by": "glasswell.ingest.shapefile:epsg_from_prj",
            "storage_epsg": 4326,
            "on_unresolved": "refuse",
            # Recorded, not assumed: the parse resolves the shipped .prj and refuses when it
            # resolves to anything but this, so a silently re-projected archive is a refusal
            # rather than a fleet of points in the wrong place.
            "measured_source_epsg": 26913,
            "declared_datum": "D North American 1983",
            "coordinate_columns_populated": HEADER_FEATURES,
        },
        "rule": (
            "The datum is read from the shipped .prj and resolved to an EPSG code; storage is"
            " EPSG:4326. A .prj that does not resolve is a refusal, never a default to 4326."
        ),
        "rationale": (
            "All three Colorado archives ship NAD_1983_UTM_Zone_13N in band, which"
            " epsg_from_prj resolves without guessing, and Wells_Metadata.html declares"
            " Horizontal_Datum_Name: D North American 1983 independently. The header also"
            " carries populated Latitude and Longitude on 100% of its rows, so the point layer"
            " needs no reprojection while the directional archives do -- which is why the"
            " transform is registered once here rather than per layer."
        ),
        "evidence_url": WELLS_METADATA_URL,
        "code_ref": "src/glasswell/ingest/co_ecmc_gis.py",
    },
    {
        "rule_id": "cr_co_wells_geometry_provenance_1",
        "source_id": WELLS_SOURCE_ID,
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
            "A Colorado well's geometry_provenance is its geom_type served verbatim, and the"
            " only geom_type this release promotes is surface."
        ),
        "rationale": (
            "geometry_provenance is a canonical column with a fixed domain and a served handle,"
            " so Colorado needs its own row for the reason New Mexico did: without it every"
            " Colorado figure carries a North Dakota rule id. Publishing the column matters as"
            " well as registering it -- the legend's provenance block reads a registered class"
            " the box does not hold as zero rather than absent, so omitting the column would"
            " assert that Colorado has no surface holes when it has 124,392."
        ),
        "evidence_url": WELLS_METADATA_URL,
        "code_ref": "src/glasswell/marts/wells.py",
    },
    {
        "rule_id": "cr_co_wells_location_qualifier_1",
        "source_id": WELLS_SOURCE_ID,
        "stage": "conform",
        "rule_kind": "vocab_map",
        "applies_to_fields": ["loc_qual"],
        "spec": {
            "target_col": "loc_qual_class",
            "case_fold": "first_token",
            "classes": list(LOC_QUAL_CLASSES),
            "measured_domain": LOC_QUAL_DOMAIN,
            "measured_classes": LOC_QUAL_CLASSES,
            "planned_share": PLANNED_SHARE,
            "planned_with_a_spud_date": PLANNED_WITH_A_SPUD_DATE,
            "planned_on_plugged": PLANNED_ON_PLUGGED,
            "planned_on_producing": PLANNED_ON_PRODUCING,
            "blank_class": "unstated",
            "orthogonal_to": "geometry_provenance",
        },
        "rule": (
            "Loc_Qual's first token, case-folded, is the location qualifier class: actual,"
            " planned, ecmc or unstated. It is a separate axis from geometry_provenance and is"
            " published as loc_qual_class."
        ),
        "rationale": (
            "geometry_provenance answers which feature a point is; Loc_Qual answers how good"
            " the coordinate is, an orthogonal axis with a disjoint vocabulary, and registering"
            " the second under the first's key would serve two answers on one screen. ECMC"
            " files sixteen distinct strings differing only in the case of the first token"
            " (ACTUAL LatLong 67,920 and Actual LatLong 806 are one class), so the rule"
            " case-folds that token and records all sixteen raw values. The number this rule"
            " exists to make citable: 44.67% of Colorado's served points, 55,570 of 124,392,"
            " are permit locations rather than surveyed ones, 27,976 of them on wells that"
            " carry a spud date, 30,369 on plugged wells and 863 on producing wells. A map that"
            " did not say so would be drawing a permit application as a well."
        ),
        "evidence_url": WELLS_METADATA_URL,
        "code_ref": "src/glasswell/marts/wells.py",
    },
    {
        "rule_id": "cr_co_wells_geometry_scope_1",
        "source_id": WELLS_SOURCE_ID,
        "stage": "conform",
        "rule_kind": "parse_directive",
        "applies_to_fields": ["all"],
        "spec": {
            "declares_fields": ["deviation", "dir_status"],
            "asserts_header": False,
            "geom_types_produced": ["surface"],
            "geom_types_staged_not_promoted": ["bottomhole", "lateral"],
            "directional_sources": [BOTTOMHOLE_SOURCE_ID, LINES_SOURCE_ID],
            "measured_wellbores": DIRECTIONAL_WELLBORES,
            "measured_wells_with_geometry": DIRECTIONAL_WELLS,
            "measured_deviation": DEVIATION_DOMAIN,
            "measured_status": {"Actual": 36063, "Planned": 2986},
            "survey_stations_published": False,
        },
        "rule": (
            "Colorado promotes the surface point and nothing else this release. The two"
            " directional archives are staged and quarantine-clean but not promoted, so a"
            " widened scope is a later rule rather than this one drifting."
        ),
        "rationale": (
            "Bottom-hole points and lateral polylines both exist, 39,049 records each, covering"
            " 37,482 of 124,392 wells -- 30.1%, so a promotion of them would leave seven wells"
            " in ten with no path and no statement of why. ECMC publishes no survey stations, so"
            " a Colorado lateral is a filed trace rather than a station path, which is a"
            " different claim from North Dakota's and needs its own decision before it is"
            " served. Deviation is Directional on 19,524, Horizontal on 15,823, Drifted on"
            " 3,347, blank on 336, Vertical on 16 and High angle on 3; Dir_Status is Actual on"
            " 36,063 and Planned on 2,986, so 2,986 of the traces are themselves plans."
        ),
        "evidence_url": DIRECTIONAL_LINES_URL,
        "code_ref": "src/glasswell/ingest/co_ecmc_gis.py",
    },
    {
        "rule_id": "cr_co_wells_effective_1",
        "source_id": WELLS_SOURCE_ID,
        "stage": "conform",
        "rule_kind": "parse_directive",
        "applies_to_fields": ["stat_date"],
        "spec": {
            "declares_fields": ["stat_date", "spud_date"],
            "asserts_header": False,
            "effective_from_field": "stat_date",
            "on_missing": "manifest_vintage",
            "promoted_to": "canonical.wells.effective_from",
            "supersession": "by effective_from ordering; canonical.wells carries no valid-time"
            " end column, so no interval is closed and none is served",
            "measured_stat_date_present": HEADER_WELLS,
            "measured_stat_date_absent": 0,
        },
        "rule": (
            "A Colorado header's valid time is Stat_Date, the date ECMC stamped the status it"
            " filed. A row with no Stat_Date takes the manifest's vintage instead."
        ),
        "rationale": (
            "canonical.wells is keyed on (api10, effective_from) and is append-only, and ECMC"
            " republishes the whole shapefile nightly. Keying on the pull would therefore"
            " append 124,392 rows every night and make the spine a log of when glasswell"
            " looked rather than of when the regulator said something. Stat_Date is the"
            " regulator's own clock for exactly the field the status vocabulary reads, so a"
            " new row appears when the status was restamped and not before. Measured, every"
            " one of the 124,392 deduplicated rows carries a Stat_Date, so the fallback fires"
            " on nothing today; it is registered because a header that arrives without one has"
            " to promote as something, and the manifest vintage is honest about being"
            " glasswell's clock rather than ECMC's."
        ),
        "evidence_url": WELLS_METADATA_URL,
        "code_ref": "src/glasswell/ingest/co_wells.py",
    },
    {
        "rule_id": "cr_co_wells_well_type_1",
        "source_id": WELLS_SOURCE_ID,
        "stage": "conform",
        "rule_kind": "parse_directive",
        "applies_to_fields": ["well_class"],
        "spec": {
            "declares_fields": ["well_class"],
            "asserts_header": False,
            "served_as": "well_type_reported",
            "decoded": False,
            "measured_domain": WELL_CLASS_DOMAIN,
            "publisher_documents_the_vocabulary": False,
        },
        "rule": (
            "Well_Class is served exactly as ECMC filed it, with no decode and no canonical"
            " class."
        ),
        "rationale": (
            "This is the honest counterpart to the status rule. The status vocabulary turned out"
            " to be published after all; the type vocabulary genuinely is not -- Wells_Metadata"
            " .html contains no Well_Class attribute at all, verified by search of the whole"
            " FGDC record, while the column carries seventeen values led by GW 37,002, OW"
            " 29,939, DA 25,396, LO 22,971 and CBM 5,421 with 1,176 blank. Inventing a decode"
            " for an undocumented code is the mapping-in-code failure R8 exists to refuse, and"
            " the well_type legend dimension already promises codes exactly as the source filed"
            " them."
        ),
        "evidence_url": WELLS_METADATA_URL,
        "code_ref": "src/glasswell/marts/wells.py",
    },
    {
        "rule_id": "cr_co_inventory_not_served_1",
        "source_id": WELLS_SOURCE_ID,
        "stage": "join",
        "rule_kind": "code_ref",
        "applies_to_fields": ["all"],
        "spec": {
            "served": False,
            "refusal": "inventory_not_served",
            "land_grid_state": False,
            "land_grid_scope": False,
            "reasons": [
                "the PLSS land grid is loaded for North Dakota's extent only",
                "no Colorado spacing-unit source is in scope",
                "the modelling that produces training_support is unbuilt",
            ],
            "module_function": "glasswell.marts.producing:no_well_series_states",
            "contract_note": "A registered refusal, not an omitted row: a consumer can tell"
            " 'no inventory decision' from 'registry not loaded'. The symbol is the"
            " producing mart's own reader of which jurisdictions have no well series,"
            " which is the shape of refusal this row is: registered, and answering.",
        },
        "rule": (
            "Colorado serves no undrilled inventory. The refusal is registered rather than"
            " omitted, and carries the three reasons it rests on."
        ),
        "rationale": (
            "Protocol 4D admits no inventory slot without geometric admissibility and a"
            " training_support score, and neither is reachable for Colorado: the PLSS land grid"
            " is loaded for North Dakota's extent only, no Colorado spacing-unit source is"
            " registered, and the modelling that produces a support score is unbuilt. An omitted"
            " row would state nothing, so a consumer could not tell a decided refusal from a"
            " registry that failed to load -- the conflation the producing mart already refuses."
            " Slots are geometrically admissible undrilled locations at an assumed spacing;"
            " nothing here produces one and nothing served may imply otherwise."
        ),
        "evidence_url": WELLS_METADATA_URL,
        "code_ref": "src/glasswell/marts/producing.py",
    },
    {
        "rule_id": "cr_co_production_liquids_1",
        "source_id": MONTHLY_SOURCE_ID,
        "stage": "conform",
        "rule_kind": "unit_conform",
        "applies_to_fields": ["oilproduced", "gasproduced", "waterproduced"],
        "spec": {
            "liquids_basis": "oil+condensate",
            "liquid_fields": ["OilProduced"],
            "condensate_field": None,
            "units": {"liquid": "bbl", "gas": "mcf", "water": "bbl"},
            "never_summed": ["OilGravity", "GasBtuSales"],
            "record_fields": 32,
        },
        "rule": (
            "Colorado's liquid stream is oil plus condensate, because ECMC files one liquid"
            " column and no condensate column exists. Gas is MCF and water is BBLS."
        ),
        "rationale": (
            "The production record dictionary lists all 32 fields and there is exactly one"
            " liquid volume, OilProduced, 'Oil produced in BBLS', beside OilSales,"
            " OilAdjustment and OilGravity; FormationCode is the only stream discriminator and"
            " it does not separate condensate. So Colorado files condensate inside its oil"
            " stream and the undifferentiation is the regulator's, not a glasswell rollup --"
            " which is the difference from New Mexico, where condensate is its own stream and"
            " the basis is oil alone. OilGravity is a sales-quality attribute and is never"
            " summed."
        ),
        "evidence_url": PRODUCTION_DICTIONARY_URL,
        "code_ref": "src/glasswell/ingest/co_production.py",
    },
    {
        "rule_id": "cr_co_production_entity_key_1",
        "source_id": MONTHLY_SOURCE_ID,
        "stage": "conform",
        "rule_kind": "key_composite",
        "applies_to_fields": ["api10", "api_sidetrack", "formation_code", "facility_id"],
        "spec": {
            "source_cols": ["api10", "api_sidetrack", "formation_code", "facility_id"],
            "separator": ":",
            "target_col": "entity_key",
            "entity_type": "well_completion_pool",
            "reporting_level": "well_completion_pool",
            "granularity": "well_observed",
            "aggregate_entity_key": "api10",
            "aggregate_entity_type": "well",
            "requires_rule_id": "cr_co_wells_api10_1",
            "on_missing": "quarantine",
            "reason_code": "key_incomplete",
            "mirrors_rule_id": "cr_nm_wcproduction_entity_key_1",
            "measured": {
                "rows": PRODUCTION_ROWS,
                "distinct_full_keys": PRODUCTION_DISTINCT_KEYS,
                "distinct_well_months": PRODUCTION_WELL_MONTHS,
                "completion_months_folded": PRODUCTION_FOLDED_MONTHS,
            },
        },
        "rule": (
            "A Colorado completion's entity_key is the API-10, the sidetrack, the formation"
            " code and the facility id joined by colons. The aggregate row that accompanies it"
            " is keyed on the API-10 alone."
        ),
        "rationale": (
            "canonical.production_monthly says composite keys are built by a key_composite rule"
            " and never by a literal in the parser, so both Colorado keys are decided here."
            " Measured over the whole rolling file the full key yields 387,813 distinct values"
            " and zero duplicates, while (API-10, year, month) collapses the same rows to"
            " 339,058 -- folding 48,755 completion-months into well-months. A key of the API-10"
            " alone would therefore either quarantine those as duplicates or silently promote"
            " them as one series. The aggregate key is North Dakota's shape rather than a second"
            " rule, so the two keys are decided in one place: the well row carries the bare"
            " API-10 and a null pool, which is what the aggregation CHECK admits."
        ),
        "evidence_url": PRODUCTION_DICTIONARY_URL,
        "code_ref": "src/glasswell/ingest/co_production.py",
    },
    {
        "rule_id": "cr_co_production_grain_1",
        "source_id": MONTHLY_SOURCE_ID,
        "stage": "conform",
        "rule_kind": "parse_directive",
        "applies_to_fields": ["all"],
        "spec": {
            "declares_fields": ["formationcode", "facilityid", "daysproduced"],
            "asserts_header": False,
            "entity_type": "well_completion_pool",
            "reporting_level": "well_completion_pool",
            "granularity": "well_observed",
            "allocation_required": False,
            "aggregation": "sum_over_pools",
            "aggregate_volume": "exact sum over the month's completion filings",
            "aggregate_days": "maximum, never the sum",
            "aggregate_null_semantics": "reported unless every completion filing is absent,"
            " then no_report",
            "single_completion_month_carries_aggregation": False,
            "cumulatives_scope": True,
            "coverage_span_note": ROLLING_SPAN_NOTE,
            "measured_span": {
                "first_month": PRODUCTION_FIRST_MONTH,
                "last_month": PRODUCTION_LAST_MONTH,
                "dense_months": PRODUCTION_DENSE_MONTHS,
                "dense_first_month": PRODUCTION_DENSE_FIRST_MONTH,
                "dense_last_month": PRODUCTION_DENSE_LAST_MONTH,
                "distinct_api10": PRODUCTION_DISTINCT_API10,
            },
            "mirrors_rule_id": "cr_nd_pool_rollup_1",
        },
        "rule": (
            "ECMC files each completion's volumes directly, so Colorado promotes one row per"
            " completion plus one well row carrying their exact sum, disclosed as"
            " sum_over_pools. There is no allocation step. A well-month with exactly one"
            " completion promotes as the well and carries no aggregation."
        ),
        "rationale": (
            "The measured key -- ApiCountyCode, ApiSequenceNumber, ApiSidetrack, FormationCode,"
            " FacilityId, ReportYear, ReportMonth -- is unique over all 387,813 rows, so the"
            " grain is per completion and not per lease: unlike Texas, where allocation is the"
            " whole problem, nothing here needs allocating. The pool rollup is glasswell's and"
            " not the regulator's, so it is disclosed rather than assumed, in the shape New"
            " Mexico registers and North Dakota implements. Days take the maximum and never the"
            " sum because a well cannot produce more days than the month holds and the"
            " completions are concurrent observations of one wellbore. Relabelling a"
            " one-completion month as an aggregate would signal a restatement that did not"
            " happen. The rolling file is the source and its span is not a life: it runs"
            " 2004-01 to 2026-06 with only seven dense months, 2025-11 to 2026-05, and a sparse"
            " tail of late filings, so a Colorado cumulative is stated over the months this file"
            " admits, which is what coverage_span_note is served for."
        ),
        "evidence_url": PRODUCTION_DICTIONARY_URL,
        "code_ref": "src/glasswell/ingest/co_production.py",
    },
    {
        "rule_id": "cr_co_production_schema_drift_1",
        "source_id": MONTHLY_SOURCE_ID,
        "stage": "parse",
        "rule_kind": "parse_directive",
        "applies_to_fields": ["all"],
        "spec": {
            "declares_fields": ["header"],
            "asserts_header": True,
            "column_resolution": "header_driven",
            "ordinal_resolution_forbidden": True,
            "aliases": {
                "GasShrinkage": ["GasSrinkage"],
                "BomInvent": ["BOMInvent"],
                "EomInvent": ["EOMInvent"],
            },
            "date_formats": ["%m/%d/%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"],
            "null_tokens": ["", "NULL"],
            "measured_rolling_columns": 32,
            "drifted_file": "2025_prod_reports.csv",
            "on_unknown_column": "quarantine",
            "reason_code": "schema_mismatch",
        },
        "rule": (
            "Every production file resolves its columns from its own header line, never by"
            " ordinal. The misspelled and re-cased aliases are registered here, two date formats"
            " are accepted and the literal string NULL is a null token."
        ),
        "rationale": (
            "The drift is not a property of the archives as a class: measured, it is in exactly"
            " one file. 1999, 2010, 2015, 2020, 2023 and 2024 all carry the rolling file's"
            " GasShrinkage spelling, MM/DD/YYYY dates and empty nulls, while"
            " 2025_prod_reports.csv carries GasSrinkage, BOMInvent and EOMInvent, FlaredVented"
            " moved ahead of WaterProduced, ISO timestamps and the literal string NULL. A"
            " positional parse would therefore read one file's water volumes as another's"
            " flared gas. Registering the aliases rather than normalising silently is what lets"
            " a reader see that two spellings were treated as one field."
        ),
        "evidence_url": PRODUCTION_DICTIONARY_URL,
        "code_ref": "src/glasswell/ingest/co_ecmc_production.py",
    },
    {
        "rule_id": "cr_co_production_vintage_1",
        "source_id": ARCHIVE_SOURCE_ID,
        "stage": "parse",
        "rule_kind": "parse_directive",
        "applies_to_fields": ["all"],
        "spec": {
            "declares_fields": ["acceptedddate", "reportyear", "reportmonth"],
            "asserts_header": False,
            "filename_year_is": "AcceptedDate",
            "filename_year_is_not": "ReportYear",
            "union_key": [
                "api10", "api_sidetrack", "formation_code", "facility_id",
                "report_year", "report_month",
            ],
            "restatement_flag": "Revised",
            "restatements_are": "appended, never applied as edits",
            "measured_revised_populated_rows": 0,
            "measured_rolling_rows": PRODUCTION_ROWS,
            "archive_years": "1999 to 2025",
            "archive_2026_present": False,
        },
        "rule": (
            "An archive filename's year is the year ECMC accepted the report, not the year it"
            " reports on, so a report month may sit in either neighbouring file and the union"
            " key is the record key, never the filename."
        ),
        "rationale": (
            "The received-year trap is confirmed rather than assumed: 2025_prod_reports.csv"
            " opens at ReportMonth 11, ReportYear 2024. A loader that keyed on the filename"
            " would double-count every month that appears in two files and lose every month"
            " that appears in neither. The 2026 file is a 404 today, which is what an accepted"
            " -year filing means at the start of a year. Revised is the restatement flag and is"
            " empty on all 387,813 rows of the rolling file, so nothing in this release exercises"
            " the restatement path; when it is populated the row is appended beside its"
            " predecessor and never applied over it."
        ),
        "evidence_url": PROD_REPORTS_URL % "2025",
        "code_ref": "src/glasswell/ingest/co_ecmc_production.py",
    },
)

# The six cadence decisions, declared here and built into rules by the scheduler's own builder
# so one grammar and one spec shape covers every job in the registry. Each states why its job
# is safe to launch from the start, which is the condition the launch exception attaches.
CO_CADENCE_DECISIONS: dict[str, dict[str, str]] = {
    "co_ecmc_gis": {
        "rule": "Pull the three ECMC GIS archives every day, the cadence their own"
        " republication stamps show.",
        "rationale": "The three archives carried last-modified stamps within seven seconds of"
        " each other, which is a nightly republication of one export rather than three"
        " independent files, and Wells_Metadata.html's own Maintenance_and_Update_Frequency"
        " says Daily. The job takes the minimum interval over its three job_sources rows, so"
        " shortening any one archive's policy shortens the job without a second decision. It is"
        " seeded launch rather than observe because no installed timer drives"
        " glasswell.ingest.co_ecmc_gis: Colorado adds no unit file, so there is no second"
        " runner to collide with, and a daily source that nothing pulls goes stale 24 hours"
        " after the deploy load and drives the platform to degraded.",
    },
    "co_ecmc_production": {
        "rule": "Pull the rolling production CSV every 35 days, the interval a monthly"
        " mid-month publication needs to be checked at.",
        "rationale": "monthly_prod.csv carries a single mid-month last-modified stamp, so the"
        " publication is monthly and a 35-day interval checks it without asserting a day ECMC"
        " has never promised. The 2.49 GB archive backfill is its own dispatch and this job"
        " pulls the rolling file only. It launches because no installed timer drives"
        " glasswell.ingest.co_ecmc_production and the Status page reports the source pending"
        " forever until something polls it.",
    },
    "co_wells": {
        "rule": "Promote the Colorado headers after the GIS ingest that stages them.",
        "rationale": "The promotion reads what staging wrote, so it reacts to the ingest rather"
        " than to a clock: a second clock over the same archive would promote a half-written"
        " staging table or skip a day the archive did move. It launches because no installed"
        " timer drives glasswell.ingest.co_wells and a promotion that never runs leaves the"
        " registration serving a tile mart with no rows behind it.",
    },
    "co_production": {
        "rule": "Promote the Colorado production month after the ingest that stages it.",
        "rationale": "The promotion is a projection of the staged rolling file and has nothing"
        " to do when the pull was unchanged, which is what a changed-trigger dependency says"
        " and a cadence cannot. It launches for the same reason its upstream does: no installed"
        " timer drives glasswell.ingest.co_production, and the well card's production series is"
        " empty until it has run once.",
    },
    "co_tiles": {
        "rule": "Refresh the Colorado tile mart after the promotions it projects.",
        "rationale": "The mart is a projection of the two promotions and is due when either"
        " moved, so it anchors on the header archive its first dependency anchors on. It"
        " launches because the deployed unit spells its tile refreshes as other modules"
        " entirely, so nothing an installed timer drives shares this entry point with it, and"
        " an unrefreshed mart serves a map layer that is empty rather than absent.",
    },
    "co_counts": {
        "rule": "Re-measure the registry's served well counts after the Colorado mart refresh.",
        "rationale": "marts.counts has no natural source of its own -- it measures whatever the"
        " registry holds -- so it anchors on the source its dependency anchors on rather than"
        " on a source it reads, and the rationale says so rather than leaving a reader to"
        " wonder. It launches because no installed timer drives glasswell.marts.counts and"
        " /v1/jurisdictions serves Colorado with no well_count and no measured_on until it has"
        " run, which is honest but permanent without this row.",
    },
}

CO_CADENCE_EVIDENCE: dict[str, str] = {
    WELLS_SOURCE_ID: WELLS_SHP_URL,
    BOTTOMHOLE_SOURCE_ID: DIRECTIONAL_BH_URL,
    LINES_SOURCE_ID: DIRECTIONAL_LINES_URL,
    MONTHLY_SOURCE_ID: MONTHLY_PROD_URL,
    ARCHIVE_SOURCE_ID: PROD_REPORTS_URL % "2025",
}


def cadence_rule_ids() -> tuple[str, ...]:
    """The six ids the migration publishes, spelled by the grammar rather than by hand."""
    from glasswell.seed.schedules import cadence_rule_id

    return tuple(cadence_rule_id(job_id) for job_id in CO_CADENCE_DECISIONS)


CO_DATA_RULE_IDS: tuple[str, ...] = tuple(str(rule["rule_id"]) for rule in CO_RULES)
CO_RULE_IDS: tuple[str, ...] = (*CO_DATA_RULE_IDS, *cadence_rule_ids())

_INSERT_RULE = """
insert into lineage.conformance_rules
    (rule_id, rule_family, supersedes_rule_id, source_id, stage, applies_to_fields, rule_kind,
     spec, rule, rationale, evidence_url, code_ref, effective_from)
values (%(rule_id)s, %(rule_family)s, %(supersedes_rule_id)s, %(source_id)s, %(stage)s,
        %(applies_to_fields)s, %(rule_kind)s, %(spec)s, %(rule)s, %(rationale)s,
        %(evidence_url)s, %(code_ref)s, %(effective_from)s)
on conflict do nothing
"""

_INSERT_STATUS = """
insert into lineage.co_facility_status_map
    (status, decode, status_canonical, published_vintage)
values (%(status)s, %(decode)s, %(status_canonical)s, %(published_vintage)s)
on conflict (status) do nothing
"""


def _row(rule: dict[str, object]) -> dict[str, object]:
    rule_id = str(rule["rule_id"])
    return {
        **rule,
        "rule_family": rule_id.rsplit("_", 1)[0],
        "spec": Jsonb(rule["spec"]),
        "supersedes_rule_id": rule.get("supersedes_rule_id"),
        "code_ref": rule.get("code_ref"),
        "evidence_url": rule.get("evidence_url"),
        "effective_from": rule.get("effective_from", EFFECTIVE_FROM),
    }


def status_map_rows() -> list[dict[str, object]]:
    """The codebook as rows, in the order ECMC's own reference list publishes it."""
    return [
        {
            "status": code,
            "decode": row["decode"],
            "status_canonical": row["status_canonical"],
            "published_vintage": EFFECTIVE_FROM,
        }
        for code, row in CO_STATUS_MAP.items()
    ]


def seed_conformance_co(connection: psycopg.Connection) -> int:
    """Rule ids are immutable: a changed decision is a new row with supersedes_rule_id."""
    with connection.cursor() as cursor:
        cursor.executemany(_INSERT_RULE, [_row(rule) for rule in CO_RULES])
        cursor.executemany(_INSERT_STATUS, status_map_rows())
        cursor.execute(
            "select count(*) from lineage.conformance_rules where rule_id = any(%s)",
            (list(CO_DATA_RULE_IDS),),
        )
        return int(cursor.fetchone()[0])
