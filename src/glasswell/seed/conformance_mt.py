"""The Montana conformance registry (SB-07 §6.2). Every rule is evidenced from a file we opened.

Every figure below was measured on 2026-08-30 by a full streaming pass over the published
archives, never sampled and never carried over from a prior survey.
"""

from __future__ import annotations

from datetime import date

import psycopg
from psycopg.types.json import Jsonb

HOST = "https://bogfiles.dnrc.mt.gov"
PRODUCTION_URL = f"{HOST}/Reporting/Production/Historical/MT_Historical_Production.zip"
WELL_LIST_URL = f"{HOST}/Reporting/Wells/MT_CompleteWellList.zip"
GIS_WELLS_URL = f"{HOST}/GISData/WellSurface/Wells.zip"
GIS_PATHS_URL = f"{HOST}/GISData/WellPaths/WellPaths.zip"

WELL_SOURCE = "mt_bogc_well_production"
PRU_SOURCE = "mt_bogc_pru_production"
GIS_WELLS_SOURCE = "mt_gis_wells"
GIS_PATHS_SOURCE = "mt_gis_well_paths"

EFFECTIVE_FROM = date(2026, 1, 1)

WELL_COLUMNS = (
    "api_wellno", "rpt_date", "st_fmtn_cd", "formation", "lease_unit", "opno", "coname",
    "bbls_oil_cond", "mcf_gas", "bbls_wtr", "days_prod", "amnd_rpt", "dt_mod",
)
PRU_COLUMNS = (
    "lease_unit", "rpt_date", "dt_receive", "amnd_rpt", "dt_amend", "opno", "coname",
    "startivn_oilcd", "oil_prod", "gas_prod", "wtr_prod", "oil_sold", "gas_sold", "oilspill",
    "wtrspill", "flarvnt_gas", "useoil", "usegas", "oilinj", "gasinj", "wtrinj", "wtrto_pit",
    "other_oil", "other_gas", "other_wtr", "dt_mod",
)
# The fifteen PRU measures with no admissible canonical stream. Named here so the staged-only
# decision is a registry fact and not an omission a reader has to notice.
PRU_DISPOSITION_COLUMNS = (
    "startivn_oilcd", "oil_sold", "gas_sold", "oilspill", "wtrspill", "flarvnt_gas", "useoil",
    "usegas", "oilinj", "gasinj", "wtrinj", "wtrto_pit", "other_oil", "other_gas", "other_wtr",
)
# The lease key sentinel. 2,208 well-grain rows carry it and 58 are blank; a non-empty test
# scores the column 99.999 percent populated, which is how it gets missed.
LEASE_UNIT_SENTINEL = "-999"

MT_RULES: tuple[dict[str, object], ...] = (
    {
        "rule_id": "cr_mt_host_pin_1",
        "source_id": WELL_SOURCE,
        "stage": "parse",
        "rule_kind": "parse_directive",
        "applies_to_fields": ["all"],
        "spec": {
            "host": "bogfiles.dnrc.mt.gov",
            "scheme": "https",
            "paths": {
                "well_production": "/Reporting/Production/Historical/MT_Historical_Production.zip",
                "pru_production": "/Reporting/Production/Historical/MT_Historical_Production.zip",
                "well_list": "/Reporting/Wells/MT_CompleteWellList.zip",
                "gis_wells": "/GISData/WellSurface/Wells.zip",
                "gis_well_paths": "/GISData/WellPaths/WellPaths.zip",
            },
            "listing_discovery": "forbidden",
            "listing_status": 403,
            "path_separator": "/",
        },
        "rule": "Fetch Montana bulk files from pinned paths; never derive a filename from a"
        " directory listing.",
        "rationale": (
            "Measured 2026-08-30: every bulk path above answers 200 with Accept-Ranges and a"
            " stable ETag, while GET / on the same host answers 403 Forbidden. There is no"
            " listing to scrape, so a pinned constant is the only reachable form and the"
            " backslash separators the MBOGC listing UI emits never enter the fetch path. The"
            " host publishes Access-Control-Allow-Origin: * on the bulk files."
        ),
        "evidence_url": PRODUCTION_URL,
    },
    {
        "rule_id": "cr_mt_well_format_1",
        "source_id": WELL_SOURCE,
        "stage": "parse",
        "rule_kind": "parse_directive",
        "applies_to_fields": ["all"],
        "spec": {
            "format_pin": "tsv",
            "container": "zip",
            "member": "MT_HistoricalWellProduction.tab",
            "delimiter": "\t",
            "line_terminator": "\r\n",
            "header_policy": "declared",
            "encoding": "utf-8",
            "expected_columns": list(WELL_COLUMNS),
            "uncompressed_bytes": 573175264,
        },
        "rule": "Read the well grain from MT_HistoricalWellProduction.tab inside"
        " MT_Historical_Production.zip: tab-delimited, CRLF, header on row one.",
        "rationale": (
            "The archive holds exactly two members and the member is selected by name, never by"
            " ordinal. Measured 5,809,609 data rows over the thirteen columns above. The file is"
            " 573,175,264 bytes uncompressed against 162 MB of free space on the ingest host, so"
            " it is streamed from the zip member and never extracted."
        ),
        "evidence_url": PRODUCTION_URL,
    },
    {
        "rule_id": "cr_mt_api_identity_1",
        "source_id": WELL_SOURCE,
        "stage": "parse",
        "rule_kind": "parse_directive",
        "applies_to_fields": ["api_wellno"],
        "spec": {
            "source_field": "API_WellNo",
            "digits": 14,
            "api10_slice": [0, 10],
            "api12_slice": [0, 12],
            "state_code": "25",
            "separators": [],
        },
        "rule": "API-10 is the first ten digits of API_WellNo; Montana's API state code is 25.",
        "rationale": (
            "API-10 is the identity spine and API-14 normalises onto it. Measured over all"
            " 5,809,608 parseable rows: API_WellNo is uniformly fourteen digits and uniformly"
            " prefixed 25, yielding 20,021 distinct API-10 values. Digits 13-14 are convention"
            " rather than PPDM-defined, which is why they are sliced off rather than trusted"
            " (§3.0.5), and the same slice is applied to every Montana source so the spine"
            " joins. separators is empty and that is a measured claim, not a default: no"
            " API_WellNo value in either production member carries display punctuation, so a"
            " literal that arrives hyphenated is a change in the source and must fail identity"
            " rather than be silently repaired."
        ),
        "evidence_url": PRODUCTION_URL,
    },
    {
        "rule_id": "cr_mt_producing_well_scope_1",
        "source_id": WELL_SOURCE,
        "stage": "parse",
        "rule_kind": "parse_directive",
        "applies_to_fields": ["api_wellno"],
        "spec": {
            "producing_api10_count": 20021,
            "gis_api10_count": 42026,
            "coverage_ratio": "0.476",
        },
        "rule": "The production file covers 20,021 wells, not the 42,027 the GIS layer carries.",
        "rationale": (
            "Recorded because the difference is a factor of two and every capacity, coverage and"
            " completeness statement keyed to the wrong one is wrong. 42,027 is the count of"
            " surface points in Wells.zip; 20,021 is the count of distinct API-10 values that"
            " ever reported production between 1986-01 and 2026-08. A Montana well having no"
            " production row is the normal case, not a gap in this ingest."
        ),
        "evidence_url": PRODUCTION_URL,
    },
    {
        "rule_id": "cr_mt_month_convention_1",
        "source_id": WELL_SOURCE,
        "stage": "parse",
        "rule_kind": "parse_directive",
        "applies_to_fields": ["rpt_date"],
        "spec": {
            "source_field": "Rpt_Date",
            "source_format": "%m/%d/%Y",
            "source_convention": "end_of_month",
            "normalised_convention": "first_of_month",
            "range": {"min": "1986-01", "max": "2026-08"},
        },
        "rule": "Rpt_Date is an end-of-month stamp for the production month and normalises to"
        " the first of that month.",
        "rationale": (
            "Rpt_Date is valid time — the month produced, never the vintage it was learned in."
            " Measured across all 5,809,608 parseable rows, every one falls on the last calendar"
            " day of its own month, including 02/28 in non-leap years and 02/29 in leap years."
            " A filing-date column would not be perfectly month-terminal across forty years, so"
            " this is a month rendered as its last day. canonical.production_monthly keys valid"
            " time on the first of the month, so the normalisation is a representation change"
            " and not a shift of the period."
        ),
        "evidence_url": PRODUCTION_URL,
    },
    {
        "rule_id": "cr_mt_knowledge_time_1",
        "source_id": WELL_SOURCE,
        "stage": "parse",
        "rule_kind": "parse_directive",
        "applies_to_fields": ["dt_mod", "amnd_rpt"],
        "spec": {
            "knowledge_field": "DT_MOD",
            "amendment_flag": "AMND_RPT",
            "flag_values": ["True", "False"],
            "amended_rows": 362006,
            "total_rows": 5809609,
        },
        "rule": "DT_MOD is knowledge time and AMND_RPT marks a filing the operator amended;"
        " neither ever moves the production month.",
        "rationale": (
            "The two clocks are independent (§3.6). Measured: AMND_RPT is the literal text True"
            " on 362,006 rows and False on 5,447,602, so amendment is a first-class 6.2 percent"
            " of the file rather than an edge case. Because the source states the amendment"
            " directly, Montana needs no vintage inference — a restatement is appended at the"
            " vintage the amended bytes were fetched, exactly as ND does, and is never applied"
            " as an edit to the row it supersedes."
        ),
        "evidence_url": PRODUCTION_URL,
    },
    {
        "rule_id": "cr_mt_lease_unit_sentinel_1",
        "source_id": WELL_SOURCE,
        "stage": "parse",
        "rule_kind": "parse_directive",
        "applies_to_fields": ["lease_unit"],
        "spec": {
            "source_field": "Lease_Unit",
            "sentinel": LEASE_UNIT_SENTINEL,
            "sentinel_rows": 2208,
            "blank_rows": 58,
            "real_rows": 5807342,
            "distinct_real_values": 8041,
            "normalises_to": None,
        },
        "rule": "Lease_Unit uses -999 to mean no lease unit; it normalises to null and never"
        " reaches an entity key.",
        "rationale": (
            "A non-empty test scores this column 99.999 percent populated and is wrong: 2,208"
            " rows carry the literal -999 and 58 are blank, leaving 5,807,342 real values over"
            " 8,041 distinct units. Treating -999 as data would mint a lease entity named -999"
            " that aggregates unrelated wells across the whole state, so the sentinel is"
            " recognised at parse and the column carries null past it."
        ),
        "evidence_url": PRODUCTION_URL,
    },
    {
        "rule_id": "cr_mt_operator_absence_1",
        "source_id": WELL_SOURCE,
        "stage": "parse",
        "rule_kind": "parse_directive",
        "applies_to_fields": ["opno", "coname"],
        "spec": {"blank_opno_rows": 847104, "total_rows": 5809609, "normalises_to": None},
        "rule": "A blank OpNo is an absent operator, not an unknown one, and is never imputed.",
        "rationale": (
            "Measured 847,104 rows with no OpNo, concentrated in the older filings. Operator is"
            " reported context on this source and not identity, so an absent value stays absent."
            " Montana carries no operator registry comparable to NM's OGRID, so any operator"
            " rollup would need an aliasing decision this rule deliberately does not make."
        ),
        "evidence_url": PRODUCTION_URL,
    },
    {
        "rule_id": "cr_mt_trailing_record_1",
        "source_id": WELL_SOURCE,
        "stage": "parse",
        "rule_kind": "parse_directive",
        "applies_to_fields": ["all"],
        "spec": {"trailing_blank_lines": 1, "action": "skip"},
        "rule": "A blank final line is end-of-file, not a record.",
        "rationale": (
            "The well member ends with one empty line. Splitting it yields a single empty field"
            " and would quarantine one parse_error per run forever, training readers to ignore a"
            " nonzero quarantine count — which is exactly the signal the blueprint's P1 exit"
            " criterion depends on staying meaningful."
        ),
        "evidence_url": PRODUCTION_URL,
    },
    {
        "rule_id": "cr_mt_volume_range_1",
        "source_id": WELL_SOURCE,
        "stage": "validate",
        "rule_kind": "validity_filter",
        "applies_to_fields": ["bbls_oil_cond", "mcf_gas", "bbls_wtr"],
        "spec": {
            "predicate_ast": {
                "and": [
                    {"or": [
                        {"is_null": {"col": "bbls_oil_cond"}},
                        {"cmp": [{"col": "bbls_oil_cond"}, ">=", {"lit": 0}]},
                    ]},
                    {"or": [
                        {"is_null": {"col": "mcf_gas"}},
                        {"cmp": [{"col": "mcf_gas"}, ">=", {"lit": 0}]},
                    ]},
                    {"or": [
                        {"is_null": {"col": "bbls_wtr"}},
                        {"cmp": [{"col": "bbls_wtr"}, ">=", {"lit": 0}]},
                    ]},
                ]
            },
            "on_fail": "quarantine",
            "reason_code": "impossible_volume",
            "measured_rejects": {"bbls_oil_cond": 388, "mcf_gas": 20, "bbls_wtr": 94},
        },
        "rule": "A reported monthly volume is never negative.",
        "rationale": (
            "Measured 502 negative measures across 5,809,609 rows — 388 oil, 94 water, 20 gas."
            " They are almost certainly corrections posted as negatives rather than parse"
            " damage, which is precisely why they are quarantined with a reason and never"
            " dropped: the ledger keeps them visible and recoverable, and a later rule can"
            " promote them as signed corrections without having to re-fetch. A null is"
            " admissible because an absent measurement is not an out-of-range one."
        ),
        "evidence_url": PRODUCTION_URL,
    },
    {
        "rule_id": "cr_mt_days_range_1",
        "source_id": WELL_SOURCE,
        "stage": "validate",
        "rule_kind": "validity_filter",
        "applies_to_fields": ["days_prod"],
        "spec": {
            "predicate_ast": {
                "or": [
                    {"is_null": {"col": "days_prod"}},
                    {"between": [{"col": "days_prod"}, {"lit": 0}, {"lit": 31}]},
                ]
            },
            "on_fail": "quarantine",
            "reason_code": "out_of_range_date",
            "measured_rejects": 1640,
            "measured_blank": 73,
        },
        "rule": "Days produced falls within a calendar month.",
        "rationale": (
            "DAYS_PROD is days produced within the report month, so 0 to 31 inclusive is the"
            " whole admissible range. Measured 1,640 rows above 31 and 73 blank. An unbounded"
            " day count is absorbed silently by any rate calculation, which is why it is"
            " rejected here rather than clamped. A blank is carried through as null and judged"
            " by the null-semantics rule, not by this one."
        ),
        "evidence_url": PRODUCTION_URL,
    },
    {
        "rule_id": "cr_mt_units_1",
        "source_id": WELL_SOURCE,
        "stage": "conform",
        "rule_kind": "unit_conform",
        "applies_to_fields": ["bbls_oil_cond", "mcf_gas", "bbls_wtr"],
        "spec": {
            "factor": "1",
            "rounding": "half_even",
            "scale": 3,
            "units": {"bbls_oil_cond": "bbl", "mcf_gas": "mcf", "bbls_wtr": "bbl"},
            "conditions_note": (
                "mcf at the regulator's stated conditions; conditions recorded, not normalised"
            ),
        },
        "rule": "Oil and water are barrels, gas is thousand cubic feet; no conversion is"
        " applied.",
        "rationale": (
            "The column names carry the units and MBOGC publishes in the same customary units"
            " canonical stores, so the factor is exactly one and is stated rather than assumed."
            " Recording an identity conversion keeps the unit on the served figure sourced from"
            " the registry rather than from a literal in serving code."
        ),
        "evidence_url": PRODUCTION_URL,
    },
    {
        "rule_id": "cr_mt_stream_vocab_1",
        "source_id": WELL_SOURCE,
        "stage": "conform",
        "rule_kind": "vocab_map",
        "applies_to_fields": ["stream_raw"],
        "spec": {
            "mapping_table": "mt_stream_promoted_map",
            "key_col": "stream_raw",
            "value_col": "stream_canonical",
            "unmapped_action": "quarantine",
            "reason_code": "stream_not_promoted",
        },
        "rule": "Map the reported measure columns onto the canonical stream vocabulary through"
        " lineage.mt_stream_map.",
        "rationale": (
            "The reported column names live in a registry table rather than in this module, so a"
            " new disposition column appearing upstream needs a row and not a code change. A"
            " column with no mapping quarantines under stream_not_promoted rather than being"
            " silently discarded, which is what keeps the PRU disposition decision auditable."
        ),
        "evidence_url": PRODUCTION_URL,
    },
    {
        "rule_id": "cr_mt_liquids_policy_1",
        "source_id": WELL_SOURCE,
        "stage": "conform",
        "rule_kind": "code_ref",
        "applies_to_fields": ["bbls_oil_cond"],
        "spec": {
            "module_function": "glasswell.ingest.mt_bogc:liquids_basis",
            "contract_note": (
                "every Montana oil figure carries basis oil+condensate; the promotion derivation"
                " records liquids_basis and the API surfaces it on the figure"
            ),
            "basis": "oil+condensate",
            "applied_by": "source",
            "canonical_stream": "oil",
            "separate_condensate_column": False,
        },
        "rule": "BBLS_OIL_COND is oil plus condensate as published; the basis travels with every"
        " figure derived from it.",
        "rationale": (
            "Montana publishes a single combined liquids column, so the project's liquid policy"
            " is pre-applied by the source rather than computed here — there is no separate"
            " condensate column to sum and none to withhold. The consequence is that a Montana"
            " oil figure is not decomposable into oil and condensate at any vintage, so the"
            " basis is mandatory on the served figure and a consumer comparing Montana oil to a"
            " state that reports the two separately is comparing different quantities unless it"
            " reads the basis."
        ),
        "evidence_url": PRODUCTION_URL,
        "code_ref": "glasswell/ingest/mt_bogc.py",
    },
    {
        "rule_id": "cr_mt_null_semantics_1",
        "source_id": WELL_SOURCE,
        "stage": "conform",
        "rule_kind": "code_ref",
        "applies_to_fields": ["bbls_oil_cond", "mcf_gas", "bbls_wtr", "days_prod"],
        "spec": {
            "module_function": "glasswell.ingest.mt_bogc:promote_well_month",
            "contract_note": (
                "null_semantics is written on every canonical.production_monthly row; a blank"
                " measure lands as no_report with volume zero, never as a reported zero"
            ),
            "states": ["reported", "reported_zero", "no_report", "withheld"],
            "blank_is": "no_report",
            "zero_is": "reported_zero",
            "measured_blank": {"bbls_oil_cond": 2, "mcf_gas": 1, "bbls_wtr": 0},
        },
        "rule": "Absent, zero and withheld are three different facts and are never collapsed.",
        "rationale": (
            "A blank measure is no_report; a literal 0 is reported_zero. Measured only three"
            " blanks in the whole well file, so the distinction is rare — and that is exactly"
            " why it must be encoded rather than left to a default, because a rule exercised"
            " three times in 5.8 million rows is one no reader will notice is missing. Montana"
            " publishes no confidentiality flag, so withheld is declared in the vocabulary but"
            " is unreachable on this source and no row is ever labelled with it."
        ),
        "evidence_url": PRODUCTION_URL,
        "code_ref": "glasswell/ingest/mt_bogc.py",
    },
    {
        "rule_id": "cr_mt_entity_key_1",
        "source_id": WELL_SOURCE,
        "stage": "conform",
        "rule_kind": "key_composite",
        "applies_to_fields": ["api10", "st_fmtn_cd"],
        "spec": {
            "source_cols": ["api10", "st_fmtn_cd"],
            "separator": ":",
            "target_col": "entity_key",
            "on_missing": "passthrough",
            "uniqueness_scope": "api10",
            "distinct_formation_codes": 313,
        },
        "rule": "A well-completion-pool key is the API-10 and the state formation code joined by"
        " a colon.",
        "rationale": (
            "ST_FMTN_CD is Montana's producing-interval label and plays the role ND's pool"
            " plays: a well reporting from two formations files two rows for the same month."
            " Measured 313 distinct codes over the file. The key is composite because neither"
            " component alone identifies the filing, and a row missing either component passes"
            " through unkeyed rather than keying on whichever half is present."
        ),
        "evidence_url": PRODUCTION_URL,
    },
    {
        "rule_id": "cr_mt_grain_uniqueness_1",
        "source_id": WELL_SOURCE,
        "stage": "conform",
        "rule_kind": "code_ref",
        "applies_to_fields": ["api10", "production_month", "st_fmtn_cd"],
        "spec": {
            "module_function": "glasswell.ingest.mt_bogc:formation_promotion_records",
            "contract_note": (
                "a group the key cannot decompose leaves its extra filings for quarantine under"
                " key_collision rather than promoting the first by file ordinal"
            ),
            "declared_key": ["api10", "production_month", "st_fmtn_cd"],
            "measured_collisions": 0,
            "measured_groups": 5809608,
            "multi_formation_well_months": 41977,
            "max_formations_per_well_month": 4,
        },
        "rule": "(API-10, production month, formation code) is unique across the whole well"
        " file.",
        "rationale": (
            "Measured zero collisions over all 5,809,608 parseable rows, so Montana has none of"
            " the undecomposable-group problem ND's pool filings raise: every filing keys"
            " cleanly. 41,977 well-months carry more than one formation, at most four, and those"
            " are the groups the rollup rule sums. A collision appearing later is a real change"
            " upstream and quarantines under key_collision rather than being resolved by"
            " spreadsheet ordinal."
        ),
        "evidence_url": PRODUCTION_URL,
        "code_ref": "glasswell/ingest/mt_bogc.py",
    },
    {
        "rule_id": "cr_mt_formation_rollup_1",
        "source_id": WELL_SOURCE,
        "stage": "conform",
        "rule_kind": "code_ref",
        "applies_to_fields": ["volume", "days_prod"],
        "spec": {
            "module_function": "glasswell.ingest.mt_bogc:formation_promotion_records",
            "contract_note": (
                "the well row carries aggregation = sum_over_pools and its volume is the exact sum"
                " of the well_completion_pool rows the same promotion wrote"
            ),
            "aggregation": "sum_over_pools",
            "volume": "sum",
            "days": "max",
            "affected_well_months": 41977,
        },
        "rule": "A well figure over several formations is the exact sum of its formation rows,"
        " disclosed as sum_over_pools; days take the maximum, never the sum.",
        "rationale": (
            "Volumes from disjoint producing intervals add. Days produced do not: a well"
            " producing 31 days from two formations produced for 31 days, not 62, and summing"
            " them manufactures a rate denominator larger than the month. The well row carries"
            " aggregation = sum_over_formations so a consumer can tell a two-formation well from"
            " a one-formation well, and the sum is a derivation over the formation rows rather"
            " than a naked sum computed at serve time."
        ),
        "evidence_url": PRODUCTION_URL,
        "code_ref": "glasswell/ingest/mt_bogc.py",
    },
    {
        "rule_id": "cr_mt_pru_format_1",
        "source_id": PRU_SOURCE,
        "stage": "parse",
        "rule_kind": "parse_directive",
        "applies_to_fields": ["all"],
        "spec": {
            "format_pin": "tsv",
            "container": "zip",
            "member": "MT_HistoricalPRUProduction.tab",
            "delimiter": "\t",
            "line_terminator": "\r\n",
            "header_policy": "declared",
            "encoding": "utf-8",
            "expected_columns": list(PRU_COLUMNS),
            "uncompressed_bytes": 186405057,
        },
        "rule": "Read the lease grain from MT_HistoricalPRUProduction.tab inside the same"
        " archive as the well grain.",
        "rationale": (
            "Both grains ship in one zip and one fetch, so they share a manifest and a vintage."
            " Measured 1,603,216 data rows over the twenty-six columns above. Montana is the"
            " only state in the catalogue that publishes well-level and unit-level monthly"
            " production from the same regulator in the same artifact."
        ),
        "evidence_url": PRODUCTION_URL,
    },
    {
        "rule_id": "cr_mt_pru_entity_key_1",
        "source_id": PRU_SOURCE,
        "stage": "conform",
        "rule_kind": "key_composite",
        "applies_to_fields": ["lease_unit"],
        "spec": {
            "source_cols": ["lease_unit"],
            "target_col": "entity_key",
            "on_missing": "quarantine",
            "entity_type": "lease",
            "charset": {"lease_unit": "digits"},
            "distinct_units": 7149,
            "sentinel": LEASE_UNIT_SENTINEL,
        },
        "rule": "The PRU entity key is the Lease_Unit number; the -999 sentinel is never a key.",
        "rationale": (
            "Lease_Unit is MBOGC's production-reporting unit identifier and is the only identity"
            " the lease grain carries — the file has no API column at all. Measured 7,149"
            " distinct units over 2001-01 to 2026-08. The sentinel exclusion is carried here as"
            " well as on the well grain because a lease entity keyed -999 would silently"
            " aggregate every unaffiliated filing in the state into one served entity."
        ),
        "evidence_url": PRODUCTION_URL,
    },
    {
        "rule_id": "cr_mt_pru_month_convention_1",
        "source_id": PRU_SOURCE,
        "stage": "parse",
        "rule_kind": "parse_directive",
        "applies_to_fields": ["rpt_date"],
        "spec": {
            "source_field": "Rpt_Date",
            "source_format": "%m/%d/%Y",
            "source_convention": "end_of_month",
            "normalised_convention": "first_of_month",
            "range": {"min": "2001-01", "max": "2026-08"},
        },
        "rule": "The PRU month convention is the well-grain convention, over a shorter history.",
        "rationale": (
            "Same end-of-month stamp, normalised the same way, so the two grains are directly"
            " comparable month for month. The range differs and that difference is load-bearing:"
            " the lease grain begins 2001-01 while the well grain begins 1986-01, so any"
            " cross-grain reconciliation is undefined for the first fifteen years and must not"
            " be reported as a disagreement there."
        ),
        "evidence_url": PRODUCTION_URL,
    },
    {
        "rule_id": "cr_mt_pru_reporting_level_1",
        "source_id": PRU_SOURCE,
        "stage": "conform",
        "rule_kind": "code_ref",
        "applies_to_fields": ["entity_key"],
        "spec": {
            "module_function": "glasswell.lineage.conformance:lease_reporting_rule",
            "contract_note": (
                "the spine and production routers read this row to label a Montana lease figure"
                " lease_reported; allocation_required false means no MT well figure is ever"
                " allocated"
            ),
            "state_code": "25",
            "reporting_level": "lease",
            "granularity": "lease_reported",
            "allocation_required": False,
        },
        "rule": "Montana PRU rows are reported at the lease and are served as lease_reported,"
        " never allocated down to wells.",
        "rationale": (
            "Which jurisdictions report at the lease is a registry fact with a date and a"
            " rationale, not a list of state codes in a serving path. Montana is unusual in that"
            " allocation is not required: the regulator already publishes the well grain"
            " directly, so a Montana well figure comes from the well file and never from an"
            " allocated lease total. allocation_required is therefore false, which distinguishes"
            " Montana from Texas, where the lease grain is the only grain there is."
        ),
        "evidence_url": PRODUCTION_URL,
        "code_ref": "glasswell/lineage/conformance.py",
    },
    {
        "rule_id": "cr_mt_pru_stream_scope_1",
        "source_id": PRU_SOURCE,
        "stage": "conform",
        "rule_kind": "code_ref",
        "applies_to_fields": list(PRU_DISPOSITION_COLUMNS),
        "spec": {
            "module_function": "glasswell.ingest.mt_bogc:promote_pru_month",
            "contract_note": (
                "only the three production measures reach canonical.production_monthly; the"
                " fifteen disposition columns remain in staging.mt_bogc_pru and are served nowhere"
            ),
            "promoted": {"oil_prod": "oil", "gas_prod": "gas", "wtr_prod": "water"},
            "staged_not_promoted": list(PRU_DISPOSITION_COLUMNS),
            "canonical_stream_vocabulary": ["oil", "gas", "water", "condensate"],
            "blocked_by": "canonical.production_monthly_stream_check",
        },
        "rule": "Only Oil_Prod, Gas_Prod and Wtr_Prod promote; the fifteen disposition columns"
        " stage faithfully and serve nothing.",
        "rationale": (
            "canonical.production_monthly constrains stream to oil, gas, water and condensate."
            " Sold, flared or vented, injected, spilled, used, other and starting inventory have"
            " no admissible value in that vocabulary, and widening it is a blueprint change"
            " rather than an ingest decision. They are staged in full so the disposition detail"
            " is not lost and a later amendment needs no re-fetch, but staging never serves, so"
            " nothing reaches an API from them. This is recorded as a scope decision rather than"
            " left as an unexplained omission of fifteen published columns."
        ),
        "evidence_url": PRODUCTION_URL,
        "code_ref": "glasswell/ingest/mt_bogc.py",
    },
    {
        "rule_id": "cr_mt_pru_stream_vocab_1",
        "source_id": PRU_SOURCE,
        "stage": "conform",
        "rule_kind": "vocab_map",
        "applies_to_fields": ["stream_raw"],
        "spec": {
            "mapping_table": "mt_stream_promoted_map",
            "key_col": "stream_raw",
            "value_col": "stream_canonical",
            "unmapped_action": "quarantine",
            "reason_code": "stream_not_promoted",
        },
        "rule": "Map the lease grain's reported measure columns through the same"
        " lineage.mt_stream_map the well grain reads.",
        "rationale": (
            "One registry serves both grains, so Oil_Prod and BBLS_OIL_COND cannot drift onto"
            " different canonical streams — which is the precondition for the cross-grain"
            " reconciliation meaning anything. The fifteen disposition columns are present in"
            " the table as unpromoted rows, so a column that stops being unpromoted is a row"
            " change rather than a code change, and one that was never registered at all"
            " quarantines under stream_not_promoted instead of vanishing."
        ),
        "evidence_url": PRODUCTION_URL,
    },
    {
        "rule_id": "cr_mt_pru_inventory_1",
        "source_id": PRU_SOURCE,
        "stage": "conform",
        "rule_kind": "code_ref",
        "applies_to_fields": ["startivn_oilcd"],
        "spec": {
            "module_function": "glasswell.ingest.mt_bogc:promote_pru_month",
            "contract_note": (
                "StartIvn_OilCd is absent from the promoted stream set, so no served figure can"
                " include it"
            ),"measure_class": "balance", "is_flow": False, "blank_rows": 18474},
        "rule": "StartIvn_OilCd is a stock balance at the start of the month, not a flow, and is"
        " never summed into production.",
        "rationale": (
            "Starting inventory is oil in tanks carried over from the prior month. Adding it to"
            " Oil_Prod double-counts barrels that were already produced in an earlier month, and"
            " summing it across months compounds the error. It is called out separately from the"
            " other staged-not-promoted columns because it is the one whose name and units make"
            " it look summable."
        ),
        "evidence_url": PRODUCTION_URL,
        "code_ref": "glasswell/ingest/mt_bogc.py",
    },
    {
        "rule_id": "cr_mt_pru_grain_uniqueness_1",
        "source_id": PRU_SOURCE,
        "stage": "conform",
        "rule_kind": "code_ref",
        "applies_to_fields": ["lease_unit", "production_month"],
        "spec": {
            "module_function": "glasswell.ingest.mt_bogc:promote_pru_month",
            "contract_note": (
                "a repeated (lease, month) key quarantines under key_collision rather than"
                " overwriting"
            ),
            "declared_key": ["lease_unit", "production_month"],
            "measured_collisions": 0,
            "measured_groups": 1603216,
        },
        "rule": "(Lease_Unit, production month) is unique across the whole PRU file.",
        "rationale": (
            "Measured zero collisions over all 1,603,216 rows, so the lease grain needs no"
            " decomposition rule and no first-by-ordinal tie-break. A collision appearing later"
            " quarantines under key_collision."
        ),
        "evidence_url": PRODUCTION_URL,
        "code_ref": "glasswell/ingest/mt_bogc.py",
    },
    {
        "rule_id": "cr_mt_pru_reconciliation_1",
        "source_id": PRU_SOURCE,
        "stage": "join",
        "rule_kind": "code_ref",
        "applies_to_fields": ["lease_unit", "production_month", "volume"],
        "spec": {
            "module_function": "glasswell.ingest.mt_bogc:promote_pru_month",
            "contract_note": (
                "the two grains are promoted under separate source ids and never averaged; this"
                " row is the measured agreement a consumer comparing them should read first"
            ),
            "join_key": ["lease_unit", "production_month"],
            "well_side": "mt_bogc_well_production.bbls_oil_cond",
            "lease_side": "mt_bogc_pru_production.oil_prod",
            "key_overlap": {"pru_units": 7149, "matched_in_well_file": 7145},
            "months_measured": ["2005-06", "2015-06", "2023-06"],
            "oil_exact_match": {"2005-06": "4673/4692", "2015-06": "5737/5766",
                                "2023-06": "5363/5386"},
            "oil_within_one_percent": {"2005-06": "4686/4692", "2015-06": "5765/5766",
                                       "2023-06": "5384/5386"},
            "scope": "measured months only",
        },
        "rule": "The well grain summed by lease reproduces the PRU lease total to the barrel on"
        " about 99.6 percent of leases in the months measured.",
        "rationale": (
            "This is the fact that makes Montana worth taking: the regulator publishes both"
            " grains, so the well file is an independent control on the lease file and the pair"
            " measures allocation error directly rather than by assumption. Measured, not"
            " assumed — 7,145 of 7,149 PRU lease units appear in the well file, and summing"
            " BBLS_OIL_COND by (Lease_Unit, month) matches Oil_Prod exactly on 99.5 to 99.6"
            " percent of leases and to within one percent on 99.9 percent, across three months"
            " spanning 2005 to 2023. The claim is scoped to those three months and names them;"
            " it is not asserted as a global rate, because only three of 308 months were"
            " measured."
        ),
        "evidence_url": PRODUCTION_URL,
        "code_ref": "glasswell/ingest/mt_bogc.py",
    },
    {
        "rule_id": "cr_mt_pru_restatement_1",
        "source_id": PRU_SOURCE,
        "stage": "parse",
        "rule_kind": "parse_directive",
        "applies_to_fields": ["amnd_rpt", "dt_amend", "dt_receive", "dt_mod"],
        "spec": {
            "amendment_flag": "Amnd_Rpt",
            "amended_rows": 64838,
            "received_field": "Dt_Receive",
            "amended_field": "Dt_Amend",
            "modified_field": "Dt_Mod",
        },
        "rule": "The PRU grain carries three knowledge dates; a restatement is appended at the"
        " fetch vintage and never applied as an edit.",
        "rationale": (
            "Dt_Receive is when MBOGC received the filing, Dt_Amend when it was amended and"
            " Dt_Mod when the record last changed — richer knowledge-time evidence than the well"
            " grain's single DT_MOD. Measured 64,838 amended rows. None of the three is the"
            " production month, and none may be used as one."
        ),
        "evidence_url": PRODUCTION_URL,
    },
    {
        "rule_id": "cr_mt_pru_null_semantics_1",
        "source_id": PRU_SOURCE,
        "stage": "conform",
        "rule_kind": "code_ref",
        "applies_to_fields": ["oil_prod", "gas_prod", "wtr_prod"],
        "spec": {
            "module_function": "glasswell.ingest.mt_bogc:promote_pru_month",
            "contract_note": (
                "null_semantics is written per promoted lease row; the unpromoted columns keep"
                " their blanks verbatim in staging"
            ),
            "states": ["reported", "reported_zero", "no_report"],
            "blank_is": "no_report",
            "measured_blank": {"oil_prod": 10, "gas_prod": 629, "wtr_prod": 819},
            "measured_blank_wtrspill": 1501840,
        },
        "rule": "Blank and zero are distinct on the lease grain exactly as on the well grain.",
        "rationale": (
            "Blank rates differ sharply by column — 10 blanks on Oil_Prod against 1,501,840 on"
            " WtrSpill, which is blank on 94 percent of rows. A single file-wide blank policy"
            " would therefore be wrong for one column or the other, so the semantics are"
            " declared per promoted column and the unpromoted columns keep their blanks verbatim"
            " in staging."
        ),
        "evidence_url": PRODUCTION_URL,
        "code_ref": "glasswell/ingest/mt_bogc.py",
    },
    {
        "rule_id": "cr_mt_pru_volume_range_1",
        "source_id": PRU_SOURCE,
        "stage": "validate",
        "rule_kind": "validity_filter",
        "applies_to_fields": ["oil_prod", "gas_prod", "wtr_prod"],
        "spec": {
            "predicate_ast": {
                "and": [
                    {"or": [
                        {"is_null": {"col": "oil_prod"}},
                        {"cmp": [{"col": "oil_prod"}, ">=", {"lit": 0}]},
                    ]},
                    {"or": [
                        {"is_null": {"col": "gas_prod"}},
                        {"cmp": [{"col": "gas_prod"}, ">=", {"lit": 0}]},
                    ]},
                    {"or": [
                        {"is_null": {"col": "wtr_prod"}},
                        {"cmp": [{"col": "wtr_prod"}, ">=", {"lit": 0}]},
                    ]},
                ]
            },
            "on_fail": "quarantine",
            "reason_code": "impossible_volume",
            "measured_rejects": {"oil_prod": 215, "gas_prod": 0, "wtr_prod": 65},
        },
        "rule": "A reported lease volume is never negative.",
        "rationale": (
            "Measured 280 negative values across the three promoted columns. The unpromoted"
            " disposition columns carry many more — 5,907 on Other_Oil alone — and are not"
            " judged here because they are never promoted; staging holds them as filed."
        ),
        "evidence_url": PRODUCTION_URL,
    },
    {
        "rule_id": "cr_mt_pru_units_1",
        "source_id": PRU_SOURCE,
        "stage": "conform",
        "rule_kind": "unit_conform",
        "applies_to_fields": ["oil_prod", "gas_prod", "wtr_prod"],
        "spec": {
            "factor": "1",
            "rounding": "half_even",
            "scale": 3,
            "units": {"oil_prod": "bbl", "gas_prod": "mcf", "wtr_prod": "bbl"},
            "conditions_note": (
                "mcf at the regulator's stated conditions; conditions recorded, not normalised"
            ),
        },
        "rule": "Lease volumes carry the same customary units as the well grain; no conversion.",
        "rationale": (
            "Stated rather than inherited from the well-grain rule, because the two grains are"
            " separate sources with separate registries and a shared assumption between them is"
            " the kind that survives a change to one side."
        ),
        "evidence_url": PRODUCTION_URL,
    },
    {
        "rule_id": "cr_mt_pru_liquids_policy_1",
        "source_id": PRU_SOURCE,
        "stage": "conform",
        "rule_kind": "code_ref",
        "applies_to_fields": ["oil_prod"],
        "spec": {
            "module_function": "glasswell.ingest.mt_bogc:liquids_basis",
            "contract_note": (
                "the lease grain shares the well grain's basis, which is why summing one to match"
                " the other agrees to the barrel"
            ),"basis": "oil+condensate", "applied_by": "source", "canonical_stream": "oil"},
        "rule": "Oil_Prod is oil plus condensate on the same basis as the well grain.",
        "rationale": (
            "The reconciliation measured above only holds because the two grains share a liquids"
            " basis: summing a combined-liquids well column to match a pure-oil lease column"
            " would not agree to the barrel on 99.6 percent of leases. The agreement is itself"
            " the evidence for this rule, and the basis is stated wherever a Montana liquid"
            " figure appears."
        ),
        "evidence_url": PRODUCTION_URL,
        "code_ref": "glasswell/ingest/mt_bogc.py",
    },
    {
        "rule_id": "cr_mt_gis_wells_format_1",
        "source_id": GIS_WELLS_SOURCE,
        "stage": "parse",
        "rule_kind": "parse_directive",
        "applies_to_fields": ["all"],
        "spec": {
            "format_pin": "esri_shapefile",
            "container": "zip",
            "layer_suffix": "wells",
            "geometry_type": "Point",
            "record_count": 42027,
            "distinct_api10": 42026,
            "null_geometries": 0,
        },
        "rule": "Read the surface points from the `wells` layer of Wells.zip.",
        "rationale": (
            "Measured 42,027 point records, none with null geometry, over 42,026 distinct API-10"
            " values. The layer is selected explicitly by stem rather than taken as the first"
            " member of the archive — see the layer-selection rule, which is why."
        ),
        "evidence_url": GIS_WELLS_URL,
    },
    {
        "rule_id": "cr_mt_gis_layer_selection_1",
        "source_id": GIS_WELLS_SOURCE,
        "stage": "parse",
        "rule_kind": "parse_directive",
        "applies_to_fields": ["all"],
        "spec": {
            "layers_per_archive": 2,
            "selected": {"Wells.zip": "wells", "WellPaths.zip": "WellPaths"},
            "rejected": {"Wells.zip": "wells_P", "WellPaths.zip": "WellPaths_P"},
            "selected_epsg": 4269,
            "rejected_epsg": 32100,
        },
        "rule": "Both MBOGC archives ship two layers; select the geographic layer by stem, never"
        " by archive order.",
        "rationale": (
            "Each zip contains a geographic layer and a NAD83 Montana StatePlane twin suffixed"
            " _P, and both carry their own .prj — 4269 and 32100 respectively, each resolving"
            " cleanly. Taking the first member per extension in sorted order happens to select"
            " the geographic layer only because '.' sorts before '_' in ASCII. That is an"
            " accident of filename collation, not a decision, and it would silently reverse if"
            " MBOGC renamed either stem. The geographic layer is chosen because canonical stores"
            " 4326 and a geographic source needs a datum shift rather than an inverse"
            " projection."
        ),
        "evidence_url": GIS_WELLS_URL,
    },
    {
        "rule_id": "cr_mt_gis_encoding_1",
        "source_id": GIS_WELLS_SOURCE,
        "stage": "parse",
        "rule_kind": "parse_directive",
        "applies_to_fields": ["coname", "well_nm"],
        "spec": {
            "dbf_encoding": "cp1252",
            "language_driver_id": "0x59",
            "reader_default": "utf-8",
            "reader_default_outcome": "raises",
        },
        "rule": "The MBOGC DBF is Windows-1252 and is read as cp1252, declared here rather than"
        " guessed by the reader.",
        "rationale": (
            "The DBF language-driver byte at offset 29 is 0x59, a Windows-1252 variant. The"
            " shared shapefile reader defaults to strict UTF-8, which raises partway through"
            " iteration on a well named Blasé — an encoding fault that surfaces as a truncated"
            " read rather than an error at open. Exactly one byte in the file falls in the"
            " 0x80-0x9F range where cp1252 and latin-1 differ, and it sits at file offset 8,"
            " inside the header-length field rather than in any text field, so cp1252 decodes"
            " all 42,027 records losslessly. The encoding is declared per source because a"
            " source that has always read as UTF-8 must not be re-decoded on this one's"
            " evidence."
        ),
        "evidence_url": GIS_WELLS_URL,
        "code_ref": "glasswell/ingest/shapefile.py",
    },
    {
        "rule_id": "cr_mt_gis_datum_1",
        "source_id": GIS_WELLS_SOURCE,
        "stage": "conform",
        "rule_kind": "datum_transform",
        "applies_to_fields": ["geom"],
        "spec": {
            "source_epsg": 4269,
            "target_epsg": 4326,
            "detect": {"prj_contains": "GCS_North_American_1983"},
        },
        "rule": "Montana GIS is NAD83 geographic and is transformed to WGS84 for storage.",
        "rationale": (
            "The shipped .prj resolves to EPSG:4269 and is read rather than assumed; a datum is"
            " never defaulted to 4326. The transform is recorded because NAD83 and WGS84 differ"
            " by up to about a metre in the continental US, which is immaterial for a map pin"
            " and material for a distance measured against a neighbour in another state stored"
            " on the other datum."
        ),
        "evidence_url": GIS_WELLS_URL,
    },
    {
        "rule_id": "cr_mt_gis_api_identity_1",
        "source_id": GIS_WELLS_SOURCE,
        "stage": "parse",
        "rule_kind": "parse_directive",
        "applies_to_fields": ["api_wellno"],
        "spec": {
            "source_field": "API_WellNo",
            "digits": 14,
            "api10_slice": [0, 10],
            "state_code": "25",
            "separators": [],
            "duplicate_api10_points": 1,
        },
        "rule": "The GIS API-10 slice is the production-file slice, so geometry and production"
        " join on one spine.",
        "rationale": (
            "Stated separately from the production identity rule because it is a separate source"
            " whose header could move independently. Measured one API-10 carrying two surface"
            " points out of 42,027, so the point layer is very nearly one-to-one with the well."
        ),
        "evidence_url": GIS_WELLS_URL,
    },
    {
        "rule_id": "cr_mt_gis_border_outliers_1",
        "source_id": GIS_WELLS_SOURCE,
        "stage": "validate",
        "rule_kind": "code_ref",
        "applies_to_fields": ["geom"],
        "spec": {
            "module_function": "glasswell.ingest.mt_gis:promote_layer",
            "contract_note": (
                "the 49 east-of-line points are promoted unchanged; nothing snaps or drops a"
                " regulator coordinate, and a cross-border neighbour count is read knowing they"
                " exist"
            ),
            "nd_mt_border_longitude": "-104.0489",
            "points_east_of_border": 49,
            "total_points": 42027,
            "action": "retain_and_disclose",
        },
        "rule": "49 Montana wells plot east of the Montana/North Dakota meridian; they are kept"
        " and disclosed, not corrected.",
        "rationale": (
            "The boundary is the 27th meridian west of Washington, about -104.0489, and it is"
            " surveyed rather than exactly meridional, so a point tens of metres east of the"
            " nominal line is not necessarily wrong. Silently snapping or dropping these would"
            " edit a regulator's coordinate on our own assumption, which raw data is never"
            " subject to. They are recorded so a cross-border neighbour count can be read"
            " knowing they exist."
        ),
        "evidence_url": GIS_WELLS_URL,
        "code_ref": "glasswell/ingest/mt_gis.py",
    },
    {
        "rule_id": "cr_mt_gis_status_vocab_1",
        "source_id": GIS_WELLS_SOURCE,
        "stage": "conform",
        "rule_kind": "vocab_map",
        "applies_to_fields": ["status"],
        "spec": {
            "mapping_table": "mt_status_promoted_map",
            "key_col": "status",
            "value_col": "status_canonical",
            "unmapped_action": "quarantine",
            "reason_code": "unknown_status",
            "source_fields": ["Status", "Type", "MapSymbol"],
            "distinct_values": 19,
            "promoted_values": 13,
            "unpromoted_values": ["Water Well, Released", "Completed", "Unknown", "Domestic",
                                  "Other", "Water Well, Completed"],
        },
        "rule": "Map the reported well Status onto the canonical status vocabulary through"
        " lineage.mt_status_map.",
        "rationale": (
            "MBOGC publishes Status, Type and MapSymbol as three parallel classifications — for"
            " example Status 'P&A - Approved' with Type 'Dry Hole' and MapSymbol 'ADH'. Status"
            " is the regulatory state and is the one mapped; the other two are retained as"
            " reported context. An unmapped status quarantines rather than defaulting, because a"
            " well silently defaulted to active is the failure mode that puts a plugged well on"
            " the map as producing. Thirteen of the nineteen published values promote. The other"
            " six are left unpromoted deliberately rather than forced: Completed is a"
            " construction milestone and not a producing state, and the production file is the"
            " authority on whether a well produced; the two water-well values and Domestic are"
            " not oil and gas wells; and Unknown and Other are the source declining to say,"
            " which is not a licence to decide on its behalf. Together they are 1,400 of 42,027"
            " points, so the quarantine rate this produces is a real signal rather than noise."
        ),
        "evidence_url": GIS_WELLS_URL,
    },
    {
        "rule_id": "cr_mt_paths_format_1",
        "source_id": GIS_PATHS_SOURCE,
        "stage": "parse",
        "rule_kind": "parse_directive",
        "applies_to_fields": ["all"],
        "spec": {
            "format_pin": "esri_shapefile",
            "container": "zip",
            "layer_suffix": "WellPaths",
            "geometry_type": "LineString",
            "dbf_encoding": "cp1252",
            "record_count": 4173,
            "fields": ["API_WellNo", "Well_Nm", "WellSub", "Formation"],
        },
        "rule": "Read the well paths from the `WellPaths` layer of WellPaths.zip.",
        "rationale": (
            "Measured 4,173 LineString records carrying exactly four attributes. The archive is"
            " twinned and cp1252 exactly as the surface-point archive is, under the same two"
            " rules."
        ),
        "evidence_url": GIS_PATHS_URL,
    },
    {
        "rule_id": "cr_mt_paths_geometry_class_1",
        "source_id": GIS_PATHS_SOURCE,
        "stage": "conform",
        "rule_kind": "code_ref",
        "applies_to_fields": ["geom"],
        "spec": {
            "module_function": "glasswell.ingest.mt_gis:promote_layer",
            "contract_note": (
                "the promotion derivation records is_directional_survey false, so"
                " geometry_provenance on every served Montana path resolves to a class that is not"
                " a survey trace"
            ),
            "geom_type": "lateral",
            "is_directional_survey": False,
            "has_measured_depth": False,
            "has_inclination": False,
            "has_azimuth": False,
            "has_station_rows": False,
            "dimensions": 2,
            "mean_vertices": "2.82",
            "vertex_histogram": {"2": 1754, "3": 1674, "4": 598, "5": 82, "6": 34, "7": 16,
                                 "8": 3, "9": 6},
            "length_ft": {"p10": 1236, "p50": 4492, "p90": 10622, "max": 23846},
        },
        "rule": "A Montana well path is a two-dimensional cartographic centreline — a map stick —"
        " and is never served, labelled or implied to be a directional survey.",
        "rationale": (
            "The layer carries no measured depth, no inclination, no azimuth and no survey"
            " stations; its four attributes are an API number, a well name, a wellbore"
            " suffix and a formation name. Measured 2.82 vertices per path on average, with"
            " 1,754 of 4,173 paths being two-point straight lines and a median length of 4,492"
            " ft against a Bakken lateral of roughly 9,500 ft. A two-point line between a"
            " surface hole and a bottom hole is a schematic, and treating it as a survey trace"
            " would attribute survey accuracy to a cartographic convenience — the error that"
            " ECMC's pre-2012 auto-generated straight lines are the standing example of. The"
            " distinction is stated wherever the geometry is served, not only here."
        ),
        "evidence_url": GIS_PATHS_URL,
        "code_ref": "glasswell/ingest/mt_gis.py",
    },
    {
        "rule_id": "cr_mt_paths_subkey_1",
        "source_id": GIS_PATHS_SOURCE,
        "stage": "conform",
        "rule_kind": "key_composite",
        "applies_to_fields": ["api10", "wellsub"],
        "spec": {
            "source_cols": ["api10", "wellsub"],
            "separator": "_",
            "target_col": "geom_key",
            "on_missing": "quarantine",
            "distinct_api10": 2836,
            "api10_with_multiple_paths": 875,
            "max_paths_per_api10": 12,
            "wellsub_values": {"LT01": 2634, "LT02": 689, "LT03": 260, "ST01": 192,
                               "WL01": 186, "LT04": 62},
        },
        "rule": "A path is keyed by API-10 and WellSub together; API-10 alone is not unique for"
        " geometry.",
        "rationale": (
            "Measured 4,173 paths over only 2,836 distinct API-10 values: 875 wells carry more"
            " than one path and one carries twelve. WellSub distinguishes laterals (LT01-LT04),"
            " sidetracks (ST01) and wellbores (WL01). Keying geometry on API-10 alone would"
            " overwrite all but one path per well, and summing path lengths per API-10 would"
            " double-count those 875 wells — the multilateral length error, one state over."
        ),
        "evidence_url": GIS_PATHS_URL,
    },
    {
        "rule_id": "cr_mt_paths_coverage_1",
        "source_id": GIS_PATHS_SOURCE,
        "stage": "conform",
        "rule_kind": "code_ref",
        "applies_to_fields": ["geom"],
        "spec": {
            "module_function": "glasswell.ingest.mt_gis:promote_layer",
            "contract_note": (
                "any figure keyed to lateral geometry covers 2,836 wells, not 20,021; the"
                " neighbour and spacing surfaces inherit that denominator"
            ),
            "api10_with_path": 2836,
            "api10_with_surface_point": 42026,
            "api10_producing": 20021,
            "path_coverage_of_producing": "0.142",
        },
        "rule": "Only 2,836 of 20,021 producing Montana wells carry a path; a well with no path"
        " has a point and no geometry beyond it.",
        "rationale": (
            "Path coverage is 14 percent of producing wells, against essentially complete"
            " surface-point coverage. Anything keyed to lateral geometry — length, spacing,"
            " neighbour edges, inventory admissibility — therefore describes a small and"
            " non-random subset of Montana, and a coverage figure stated against the well count"
            " rather than the path count would overstate it sevenfold. Recorded so the limit is"
            " read off the registry rather than discovered from a sparse map."
        ),
        "evidence_url": GIS_PATHS_URL,
        "code_ref": "glasswell/ingest/mt_gis.py",
    },
    {
        "rule_id": "cr_mt_paths_datum_1",
        "source_id": GIS_PATHS_SOURCE,
        "stage": "conform",
        "rule_kind": "datum_transform",
        "applies_to_fields": ["geom"],
        "spec": {
            "source_epsg": 4269,
            "target_epsg": 4326,
            "detect": {"prj_contains": "GCS_North_American_1983"},
        },
        "rule": "Well paths are NAD83 geographic and are transformed to WGS84 for storage.",
        "rationale": (
            "The path archive ships its own .prj and it is read on its own terms rather than"
            " inherited from the surface-point archive, because the two are separately"
            " maintained files that happen to agree today."
        ),
        "evidence_url": GIS_PATHS_URL,
    },
    {
        "rule_id": "cr_mt_basin_scope_1",
        "source_id": WELL_SOURCE,
        "stage": "conform",
        "rule_kind": "code_ref",
        "applies_to_fields": ["basin"],
        "spec": {
            "module_function": "glasswell.ingest.mt_bogc:promote_well_month",
            "contract_note": (
                "canonical.wells.basin stays null for Montana, so the type-curve peer ladder"
                " cannot draw a Madison or Cut Bank well into a Williston rung"
            ),
            "basin_assigned": None,
            "formation_row_counts": {"MAD": 999523, "EAG": 881764, "CB": 509961, "BI": 277879,
                                     "BAK": 266133},
            "bakken_share": "0.046",
            "distinct_formation_codes": 313,
        },
        "rule": "Montana wells are promoted with no basin tag; the Williston label is not"
        " extended across the state line by default.",
        "rationale": (
            "Montana is commonly described as an extension of the Williston because of the Elm"
            " Coulee Bakken, and for that corner it is. Statewide it is not: measured over the"
            " whole file, Bakken is the fifth formation by row count at 266,133 rows, 4.6"
            " percent, behind Madison at 999,523, Eagle at 881,764, Cut Bank at 509,961 and Bow"
            " Island at 277,879, across 313 distinct codes. Tagging every Montana well"
            " basin=williston would put Madison and Cut Bank wells into the peer ladder the type"
            " curve builds on formation_area_length, formation_area and formation_basin, and"
            " corrupt the control it exists to provide. A basin assignment for Montana is a"
            " separate evidenced decision — most likely per formation rather than per state —"
            " and is deliberately not made here."
        ),
        "evidence_url": PRODUCTION_URL,
        "code_ref": "glasswell/ingest/mt_bogc.py",
    },
    {
        "rule_id": "cr_mt_well_list_scope_1",
        "source_id": GIS_WELLS_SOURCE,
        "stage": "parse",
        "rule_kind": "parse_directive",
        "applies_to_fields": ["all"],
        "spec": {
            "artifact": "MT_CompleteWellList.zip",
            "member": "MT_HistoricalWellList.tab",
            "reachable": True,
            "ingested": False,
        },
        "rule": "MT_CompleteWellList.tab is reachable and is not ingested in this slice.",
        "rationale": (
            "The header file carries permit, spud, completion and slant columns that would"
            " enrich the well card and supply a completion anchor independent of FracFocus."
            " It is recorded as reachable, with its member name, so the decision not to take it"
            " is visible as a scope choice with a date rather than as an oversight."
        ),
        "evidence_url": WELL_LIST_URL,
    },
    {
        "rule_id": "cr_mt_paths_length_scope_1",
        "source_id": GIS_PATHS_SOURCE,
        "stage": "conform",
        "rule_kind": "validity_filter",
        "applies_to_fields": ["geom", "lateral_length_ft"],
        "spec": {
            "module_function": "glasswell.api.routers.wells:get_well",
            "contract_note": (
                "lateral_length_ft is null for every Montana well and the response carries this"
                " rule id as the reason; no Montana mart publishes a length column either"
            ),
            "length_method": "not_served",
            "basin_assigned": None,
            "length_rule_source_if_defaulted": "nd_gis_horizontals_line",
            "wellsub_values_summed_if_served": ["LT01", "LT02", "LT03", "LT04", "ST01", "WL01"],
            "api10_with_multiple_paths": 875,
            "vertical_wellbore_paths": 186,
            "sidetrack_paths": 192,
        },
        "rule": "No lateral length is served for a Montana well; the figure is withheld and this"
        " rule is what the response cites in its place.",
        "rationale": (
            "Two independent reasons, either sufficient. First, lengths.resolve_length_method is"
            " keyed by basin and cr_mt_basin_scope_1 leaves Montana untagged, so the default"
            " path resolves North Dakota's nd_gis_horizontals_line rule — a Montana figure"
            " would carry a handle resolving to a rule about North Dakota geometry, which is the"
            " naked-number failure R8 exists to prevent. Second, the figure would be a sum of"
            " path lengths per API-10, and cr_mt_paths_subkey_1 measured that 875 wells carry"
            " more than one path, so the sum double-counts them; 186 of the 4,173 paths are"
            " WL01 vertical wellbores and 192 are ST01 sidetracks, neither of which is a lateral"
            " whose plan-view length means what the field name says. Withholding is not a gap:"
            " the geometry is still served and still drawn, and a consumer that needs a length"
            " can measure the served line under a method of its own choosing and its own name."
        ),
        "evidence_url": GIS_PATHS_URL,
        "code_ref": "glasswell/api/routers/wells.py",
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


def seed_conformance_mt(connection: psycopg.Connection) -> int:
    """Rule ids are immutable: a change is a new row with supersedes_rule_id (SB-07 §6.2)."""
    with connection.cursor() as cursor:
        cursor.executemany(_INSERT, [_row(rule) for rule in MT_RULES])
        # Counted per jurisdiction, so the number does not depend on what else seed_all ran.
        cursor.execute(
            "select count(*) from lineage.conformance_rules where source_id like 'mt\\_%%'"
        )
        return int(cursor.fetchone()[0])
