"""The ND vintage-cohort key, as a row (R8). No query decides which year a cohort is keyed on.

Spud year and completion-anchor year are not two names for one chart: of the ND wells that
carry both dates, 47 percent fall in different years. A serving path that picked one silently
would be picking a different chart, so the choice, its measured basis and the alternative it
rejects live here and are served at /v1/conformance/cr_nd_vintage_cohort_1.
"""

from __future__ import annotations

from datetime import date

import psycopg
from psycopg.types.json import Jsonb

from glasswell.seed.conformance_nd import GIS_WELLS_URL

# The day the branch lands and the distributions below were measured against the deployed
# instance.
VINTAGE_FROM = date(2026, 8, 30)

COHORT_READER = "glasswell.marts.vintage_cohorts:load_cohort_policy"

VINTAGE_RULES: tuple[dict[str, object], ...] = (
    {
        "rule_id": "cr_nd_vintage_cohort_1",
        "source_id": "nd_gis_wells",
        "stage": "conform",
        "rule_kind": "code_ref",
        "applies_to_fields": ["spud_date"],
        "spec": {
            "module_function": COHORT_READER,
            "version": "1",
            "contract_note": (
                "returns the cohort key, the column it is read from and the label the no-key"
                " cohort is served under; the serving path groups on that key and never"
                " chooses one itself. support_measure below is the second decision this rule"
                " governs: which wells count as standing behind a cohort's totals"
            ),
            "cohort_key": "spud_year",
            "cohort_key_field": "canonical.wells_latest.spud_date",
            "null_cohort_label": "no_spud_date",
            "vintage_read_at": "wells_latest_effective_row",
            "rejected_alternatives": [
                {
                    "cohort_key": "completion_anchor_year",
                    "why_not": (
                        "It covers 17,563 of 43,817 ND wells against the spud date's 36,847,"
                        " and its earliest value is 2009-06-06 because that is when the"
                        " FracFocus registry began, not when the basin was drilled. A cohort"
                        " chart on that key shows zero wells before 2009 and reads as history."
                    ),
                }
            ],
            "measured_on": "2026-08-30",
            "coverage": {
                "population": 43817,
                "spud_year": 36847,
                "completion_anchor_year": 17563,
                "null_cohort": 6970,
                "null_cohort_with_a_filed_month": 49,
            },
            "disagreement": {
                "both_dates": 17520,
                "different_year": 8214,
                "median_lag_days": 150,
            },
            "support_measure": {
                "field": "wells_with_a_filed_month",
                "definition": (
                    "a well in the cohort whose canonical record carries at least one month"
                    " admitted into a cumulative total — null_semantics reported or"
                    " reported_zero — in any stream"
                ),
                "why_not_the_producing_classification": (
                    "cr_producing_window_1, cr_producing_streams_1 and cr_producing_evidence_1"
                    " define whether a well is producing now, over a three-month window ending"
                    " at the newest filed month, on oil and gas only. That is a different"
                    " question from how many wells stand behind a cohort's all-time totals: it"
                    " would report the 1958 cohort as almost empty and would tell a reader"
                    " nothing about the support under the figures this response serves. The"
                    " field is named for what it counts rather than for that classification,"
                    " so the two are not mistaken for one another."
                ),
                "excludes": (
                    "a well whose only filings are no_report or withheld rows, which is the"
                    " same set the cumulative admits nothing from; a filed zero is a filing and"
                    " is counted"
                ),
                "measured": {
                    "cohorts": 94,
                    "max_cohort": 2553,
                    "section_scale_largest_class": 73,
                    "band_histogram": [16, 6, 43, 20, 9],
                },
            },
            "support_bands": ["0", "1-9", "10-99", "100-999", "1000+"],
            "support_band_basis": (
                "Cohort scale. Over the 94 ND spud-year cohorts the wells_with_a_filed_month"
                " count runs 0 to 2,553, so the PLSS section bands used by the land-grid"
                " rollups put 73 of the 94 in one class."
            ),
        },
        "code_ref": COHORT_READER,
        "rule": "ND vintage cohorts are keyed on the year the well was spudded.",
        "rationale": (
            "Four measured grounds, all read from the deployed instance on 2026-08-30."
            " Coverage: spud dates cover 36,847 of the 43,817 ND wells (84.1 percent) while the"
            " FracFocus completion anchor covers 17,563 (40.1 percent); 19,327 wells carry a"
            " spud date and no anchor, 43 carry an anchor and no spud date, so keying on the"
            " anchor would discard 44 percent of the population."
            " The anchor's floor is a fact about the registry rather than about drilling: the"
            " earliest anchor is 2009-06-06 and the earliest spud date is 1922-04-07, so a"
            " completion-anchor cohort chart shows an empty basin before 2009."
            " canonical.wells.completion_date is populated only by"
            " fracfocus.materialize_nd_readiness, which is why its coverage is exactly the"
            " anchor's."
            " The choice is real, which is why it is a rule: of the 17,520 wells carrying both"
            " dates, 8,214 (46.9 percent) fall in different years, with a median spud-to-"
            "completion lag of 150 days."
            " The cost is stated rather than hidden: 6,970 wells (15.9 percent) have no spud"
            " date and are served as an explicit cohort with cohort_year null and"
            " cohort_key_semantics no_spud_date, never folded into a year and never dropped."
            " Of those, 49 carry at least one month admitted into a total, so the cohort is"
            " large in count and small in volume, and the response says both."
            " The glossary is reconciled rather than contradicted: gt_vintage_well_vintage"
            " keeps the industry meaning in its short definition and states this key choice in"
            " its expanded text, and gt_spud_date already warns that a spud-date cohort should"
            " say which vintage it read them at, so the response reports spud_dates_read_at."
            " Restatement risk is disclosed: spud dates are among the fields most often later"
            " corrected, canonical.wells is effective-dated and wells_latest takes the newest"
            " effective row, so two runs that disagree are explicable rather than mysterious."
        ),
        "evidence_url": GIS_WELLS_URL,
        "effective_from": VINTAGE_FROM,
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
        "effective_from": rule.get("effective_from", VINTAGE_FROM),
    }


def seed_conformance_vintage(connection: psycopg.Connection) -> int:
    """Counted by rule id, not by source: this row shares nd_gis_wells with the ND registry,
    and a source-wide count here would move whenever that registry grew."""
    with connection.cursor() as cursor:
        cursor.executemany(_INSERT, [_row(rule) for rule in VINTAGE_RULES])
        cursor.execute(
            "select count(*) from lineage.conformance_rules where rule_id = any(%s)",
            ([str(rule["rule_id"]) for rule in VINTAGE_RULES],),
        )
        return int(cursor.fetchone()[0])
