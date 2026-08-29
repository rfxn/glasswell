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
