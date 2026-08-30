"""FracFocus disclosure rules pinned from the archive's own data dictionary."""

from __future__ import annotations

from datetime import date

import psycopg
from psycopg.types.json import Jsonb

DOWNLOAD_URL = "https://www.fracfocusdata.org/digitaldownload/FracFocusCSV.zip"
TERMS_URL = "https://fracfocus.org/terms"
EFFECTIVE_FROM = date(2026, 8, 26)

FRACFOCUS_RULES: tuple[dict[str, object], ...] = (
    {
        "rule_id": "cr_ff_disclosure_parse_1",
        "rule_family": "cr_ff_disclosure_parse",
        "source_id": "fracfocus_csv",
        "stage": "parse",
        "rule_kind": "parse_directive",
        "applies_to_fields": ["DisclosureList_1.csv"],
        "spec": {
            "member": "DisclosureList_1.csv",
            "encoding": "utf-8-sig",
            "all_columns": "text",
            "timestamp_formats": [
                "%m/%d/%Y %I:%M:%S %p",
                "%m/%d/%Y",
                "%Y-%m-%d",
            ],
            "member_stream": True,
        },
        "rule": "Stream DisclosureList_1.csv from the archive and retain source text in staging.",
        "rationale": (
            "The 440 MB archive expands beyond 3 GiB. Streaming one member keeps the source"
            " artifact immutable and avoids materialising all members together; every member"
            " is still decompressed once for its manifest SHA-256 inventory."
        ),
        "evidence_url": DOWNLOAD_URL,
        "code_ref": None,
        "effective_from": EFFECTIVE_FROM,
    },
    {
        "rule_id": "cr_ff_api_identity_1",
        "rule_family": "cr_ff_api_identity",
        "source_id": "fracfocus_csv",
        "stage": "parse",
        "rule_kind": "parse_directive",
        "applies_to_fields": ["APINumber"],
        "spec": {
            "digits": 14,
            "api10_slice": [0, 10],
            "nd_state_code": "33",
            "state_name": "North Dakota",
        },
        "rule": "Normalize the published API-14 and use its first ten digits as well identity.",
        "rationale": (
            "The bundled data dictionary defines APINumber as xx-xxx-xxxxx-00-00 and StateName"
            " as calculated from it. Requiring both the 33 prefix and North Dakota label turns"
            " a disagreement into quarantine instead of silently crossing jurisdictions."
        ),
        "evidence_url": DOWNLOAD_URL,
        "code_ref": None,
        "effective_from": EFFECTIVE_FROM,
    },
    {
        "rule_id": "cr_ff_api_identity_2",
        "rule_family": "cr_ff_api_identity",
        "supersedes_rule_id": "cr_ff_api_identity_1",
        "source_id": "fracfocus_csv",
        "stage": "parse",
        "rule_kind": "parse_directive",
        "applies_to_fields": ["APINumber"],
        "spec": {
            "digits": 14,
            "api10_slice": [0, 10],
            "separators": ["-", " "],
            "nd_state_code": "33",
            "state_name": "North Dakota",
        },
        "rule": (
            "Normalize the published API-14 by removing the documented display separators,"
            " require fourteen digits, and use the first ten as well identity."
        ),
        "rationale": (
            "cr_ff_api_identity_1 said normalize and declared the digit count and the slice, but"
            " never said what a separator is, and three loaders read that silence differently:"
            " this source and the ND MPR deleted every non-digit character while the ND"
            " directional survey demanded fourteen bare digits, so 33-043-00002-00-00 was an"
            " identity under one rule and key_incomplete under another. What this archive's"
            " api10 reaches is canonical.well_completion_anchors, which meets the wells spine"
            " and the ND lateral geometry rather than a survey-keyed row, so the defect claimed"
            " here is the disagreement itself: two rules reading one published form two ways,"
            " with neither row saying which was meant. The separators are declared, and"
            " declared as these two characters, because the archive's own bundled data"
            " dictionary defines APINumber as xx-xxx-xxxxx-00-00: the hyphenated literal is the"
            " published form and refusing it would reject the format the publisher documents."
            " Deleting every non-digit instead of the declared pair is what made the old reading"
            " unsafe - it keyed 'API 33053039010000' and '33053039010000 (amended)' onto a real"
            " well, the same invention cr_tx_api10_build_1 already refuses through its charset"
            " bound. Valid time is the ancestor's, because this states what an API literal in"
            " this archive has always been rather than changing it from today; knowledge time"
            " carries the correction date, which is what the second clock is for."
        ),
        "evidence_url": DOWNLOAD_URL,
        "code_ref": None,
        "effective_from": EFFECTIVE_FROM,
    },
    {
        "rule_id": "cr_ff_completion_anchor_1",
        "rule_family": "cr_ff_completion_anchor",
        "source_id": "fracfocus_csv",
        "stage": "conform",
        "rule_kind": "code_ref",
        "applies_to_fields": ["JobStartDate", "JobEndDate", "completion_date"],
        "spec": {
            "module_function": "glasswell.ingest.fracfocus:materialize_nd_readiness",
            "version": "1",
            "source_field": "JobEndDate",
            "anchor_kind": "hydraulic_frac_job_end",
            "well_selection": "earliest_valid_job_end_per_api10",
            "reject_if": ["job_end_missing", "job_end_before_job_start"],
            "forbidden_proxies": ["spud_date", "first_production_month"],
            "contract_note": (
                "materialize_nd_readiness selects min(JobEndDate) per API-10 from current"
                " disclosure observations and never coalesces spud or production dates"
            ),
        },
        "rule": (
            "Use the earliest valid FracFocus hydraulic-fracturing JobEndDate as the ND"
            " pre-production completion anchor."
        ),
        "rationale": (
            "FracFocus's bundled data dictionary defines JobEndDate as the date the hydraulic"
            " fracturing job was completed, excluding teardown. It is a completion event, not"
            " a spud or production proxy. The earliest event is selected because later"
            " disclosures can be refractures; every disclosure remains in canonical so that"
            " choice is inspectable. ND's free OGD well extract has no completion date, while"
            " the regulator's completion-bearing Well Index is subscription-only."
        ),
        "evidence_url": DOWNLOAD_URL,
        "code_ref": "glasswell.ingest.fracfocus:materialize_nd_readiness",
        "effective_from": EFFECTIVE_FROM,
    },
    {
        "rule_id": "cr_ff_base_water_units_1",
        "rule_family": "cr_ff_base_water_units",
        "source_id": "fracfocus_csv",
        "stage": "conform",
        "rule_kind": "unit_conform",
        "applies_to_fields": ["TotalBaseWaterVolume"],
        "spec": {
            "unit": "gal",
            "unit_label": "US gallons",
            "evidence": "bundled data dictionary",
            "measured_on": "2026-08-30",
            "measured": {
                "nd_rows_with_volume": 16940,
                "p50_gal": 6342549,
                "p50_nd_lateral_ft": 10153,
                "implied_gal_per_ft": 625,
            },
        },
        "rule": "TotalBaseWaterVolume is US gallons, and every served figure says so.",
        "rationale": (
            "The archive's bundled data dictionary states gallons, and the arithmetic"
            " corroborates it rather than taking the column name on trust. Measured on the"
            " deployed instance 2026-08-30, the ND median TotalBaseWaterVolume is 6,342,549 and"
            " the ND median summed lateral is 10,153 ft, so the implied intensity is about 625"
            " gal/ft, which is 14.9 bbl/ft - an ordinary Bakken number across a 2011-2026 mix."
            " Read as barrels the same pair implies about 26,300 gal/ft, which is not a"
            " completion any operator has pumped. A unit assumed from a column name is exactly"
            " the class of error R8 exists to catch, so both the dictionary and the arithmetic"
            " are recorded here."
        ),
        "evidence_url": DOWNLOAD_URL,
        "code_ref": None,
        "effective_from": EFFECTIVE_FROM,
    },
    {
        "rule_id": "cr_ff_design_promote_1",
        "rule_family": "cr_ff_design_promote",
        "source_id": "fracfocus_csv",
        "stage": "conform",
        "rule_kind": "code_ref",
        "applies_to_fields": ["TotalBaseWaterVolume"],
        "spec": {
            "module_function": "glasswell.ingest.fracfocus:_promote_design",
            "version": "1",
            "contract_note": (
                "_promote_design classifies each ND disclosure's TotalBaseWaterVolume, promotes"
                " the value with its null semantics, and quarantines a non-numeric literal or"
                " one above the plausibility bound rather than promoting it"
            ),
            "source_field": "TotalBaseWaterVolume",
            "null_semantics": {"blank": "no_report", "zero": "reported_zero"},
            "plausibility_max_gal": 50000000,
            "reject_if": ["non_numeric", "exceeds_plausibility"],
            "reject_reason_codes": ["parse_error", "impossible_volume"],
            "measured_on": "2026-08-30",
            "measured": {
                "nd_rows": 18693,
                "nd_rows_with_volume": 16940,
                "nd_rows_numeric": 16940,
                "nd_rows_zero": 37,
                "p99_gal": 21119549,
                "max_gal": 188222862,
                "excluded_above_bound": 7,
            },
        },
        "rule": (
            "Promote the disclosed base water volume with its null semantics; quarantine a"
            " non-numeric literal or one above the plausibility bound."
        ),
        "rationale": (
            "A blank is a fact about the source, not a reject: it promotes as no_report with a"
            " null volume, so absence is never inferred as zero and a filed zero (37 ND rows on"
            " the 2026-08-30 load) stays a separate served fact. The plausibility bound is where"
            " judgement is needed and it is measured rather than asserted: 16,940 ND rows carry"
            " a numeric volume, their p99 is 21,119,549 gal and their maximum is 188,222,862 -"
            " 8.9 times the p99, which is a disclosure covering more than one well or a units"
            " error, and either way it is not this well's completion. The bound is 50,000,000"
            " gal, 2.4 times the p99, and it excludes 7 of the 16,940 rows (0.04 percent); those"
            " 7 are quarantined as impossible_volume rather than dropped, joining an existing"
            " path rather than opening one. Moving the bound later is a superseding rule row"
            " with its own effective date, never an edit."
        ),
        "evidence_url": DOWNLOAD_URL,
        "code_ref": "glasswell.ingest.fracfocus:_promote_design",
        "effective_from": EFFECTIVE_FROM,
    },
    {
        "rule_id": "cr_ff_fluid_intensity_1",
        "rule_family": "cr_ff_fluid_intensity",
        "source_id": "fracfocus_csv",
        "stage": "conform",
        "rule_kind": "code_ref",
        "applies_to_fields": ["base_water_volume", "lateral_length_ft"],
        "spec": {
            "module_function": "glasswell.api.routers.completions:_fluid_intensity",
            "version": "1",
            "contract_note": (
                "_fluid_intensity reads min_lateral_ft and max_gal_per_ft from this spec at"
                " request time and returns a value with a reason, never a number with no reason"
            ),
            "expression": "base_water_volume_gal / lateral_length_ft",
            "unit": "gal/ft",
            "min_lateral_ft": 1000,
            "max_gal_per_ft": 5000,
            "null_semantics_vocabulary": [
                "reported",
                "no_report",
                "lateral_length_unavailable",
                "lateral_length_implausible",
                "intensity_out_of_range",
                "intensity_rule_unregistered",
            ],
            "measured_on": "2026-08-30",
            "measured": {
                "nd_lateral_wells": 22263,
                "min_summed_lateral_ft": 0.24,
                "wells_at_exactly_zero_ft": 0,
                "wells_under_1000_ft": 583,
                "p50_summed_lateral_ft": 10153,
                "computable": 15684,
                "excluded_by_min_lateral_ft": 325,
                "excluded_by_max_gal_per_ft": 64,
                "p50_gal_per_ft": 662.7,
            },
        },
        "rule": (
            "Fluid intensity is the disclosed base water volume over the summed lateral, served"
            " only where the divisor is at least 1,000 ft and the result is at most 5,000"
            " gal/ft."
        ),
        "rationale": (
            "A divide-by-zero guard would fire on nothing here and that is what makes this"
            " dangerous. Measured on the live geodesic path on 2026-08-30 - the same"
            " sum(ST_Length(geom::geography)) the card computes - no ND well has a summed"
            " lateral of exactly zero; the minimum is 0.24 ft over 22,263 wells. Against the"
            " median ND disclosure of 6.34 M gal, 0.24 ft serves 26.4 million gal/ft as a figure"
            " with a unit, a handle and a resolvable chain, and no reason code anywhere."
            " 583 of the 22,263 sit under 1,000 ft, where the number is implausible without"
            " being absurd, which is worse. So the divisor is bounded at 1,000 ft: a tenth of"
            " the ND median summed lateral of 10,153 ft is a geometry defect or a"
            " wrong-wellbore disclosure, not a very intense completion. That bound withdraws"
            " the figure for 325 of the 15,684 wells whose intensity is otherwise computable"
            " (2.07 percent), each with lateral_length_implausible stated rather than a number."
            " The result is bounded too, at 5,000 gal/ft - 119 bbl/ft, about 7.5 times the"
            " measured ND median of 662.7 gal/ft and beyond any job on record - which withdraws"
            " a further 64 of the 15,359 that clear the floor (0.42 percent) as"
            " intensity_out_of_range. Nulling 2.5 percent with a stated reason beats serving"
            " 26 M gal/ft with a handle. This is a serve-time rule and not part of"
            " cr_ff_design_promote_1 because the divisor is computed at request time from live"
            " geometry and the promotion never sees it; a rule that did not describe what it"
            " governs would be worse than no rule. Moving either bound is a superseding row"
            " with its own effective date. The last vocabulary member is the state where this"
            " rule itself is absent: with no bounds registered there is nothing to apply, and"
            " the response says the registry is missing rather than reporting no_report, which"
            " would state that the source disclosed nothing."
        ),
        "evidence_url": DOWNLOAD_URL,
        "code_ref": "glasswell.api.routers.completions:_fluid_intensity",
        "effective_from": EFFECTIVE_FROM,
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


def seed_conformance_fracfocus(connection: psycopg.Connection) -> int:
    with connection.cursor() as cursor:
        cursor.executemany(
            _INSERT,
            [
                {
                    **rule,
                    "spec": Jsonb(rule["spec"]),
                    "supersedes_rule_id": rule.get("supersedes_rule_id"),
                }
                for rule in FRACFOCUS_RULES
            ],
        )
        cursor.execute(
            "select count(*) from lineage.conformance_rules where source_id = 'fracfocus_csv'"
        )
        return int(cursor.fetchone()[0])
