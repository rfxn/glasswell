"""The producing definition, as rows (R8). No serving path decides any of this for itself.

Administratively active and actually producing are different facts, and the difference is a
definition rather than a lookup: which months count, which streams count, and what a filed
zero means beside an absent filing. Each of those is a decision with a rationale and a date,
so each is a rule row here and `glasswell.marts.producing` reads them at serve time.
"""

from __future__ import annotations

from datetime import date

import psycopg
from psycopg.types.json import Jsonb

from glasswell.seed.conformance_nd import MPR_FILE_URL, MPR_INDEX_URL

# The day the ND back-load completed and the distributions below were measured against it.
PRODUCING_FROM = date(2026, 8, 23)

POLICY_READER = "glasswell.marts.producing:load_producing_policy"

PRODUCING_RULES: tuple[dict[str, object], ...] = (
    {
        "rule_id": "cr_producing_window_1",
        "source_id": "nd_mpr_xlsx",
        "stage": "conform",
        "rule_kind": "code_ref",
        "applies_to_fields": ["production_month"],
        "spec": {
            "module_function": POLICY_READER,
            "version": "1",
            "contract_note": (
                "returns window_months and anchor; the serving path computes the window start"
                " from them and never from the wall clock"
            ),
            "window_months": 3,
            "anchor": "latest_available_production_month",
            "window_inclusive_of_anchor": True,
        },
        "code_ref": POLICY_READER,
        "rule": "A well is judged over the newest filed month and the two before it.",
        "rationale": (
            "Two decisions, both measured on the 2026-08-23 load. The anchor is the newest"
            " month in canonical.production_monthly, not today: the monthly report runs about"
            " five months behind the calendar (131 months are loaded, 2015-05 to 2026-03,"
            " against a wall clock of 2026-08), so anchoring on today asks for months nobody"
            " has filed and would class every well not-producing. The span is three months"
            " because the marginal well count flattens there: of 20,643 wells North Dakota"
            " calls active, 18,625 show positive hydrocarbon volume in the anchor month alone,"
            " 18,980 within three months, 19,173 within six and 19,303 within twelve. The first"
            " step is worth 355 wells and absorbs a single late or skipped filing; the next"
            " two are worth 193 and 130 and buy that at the price of calling a well producing"
            " on a filing three seasons stale. Twelve months would report a well that last"
            " produced in early 2025 the same as one that produced last month, which is the"
            " distinction this filter exists to draw."
        ),
        "evidence_url": MPR_INDEX_URL,
        "effective_from": PRODUCING_FROM,
    },
    {
        "rule_id": "cr_producing_streams_1",
        "source_id": "nd_mpr_xlsx",
        "stage": "conform",
        "rule_kind": "code_ref",
        "applies_to_fields": ["stream"],
        "spec": {
            "module_function": POLICY_READER,
            "version": "1",
            "contract_note": (
                "returns qualifying_streams and the liquids basis that travels with every"
                " figure the classes are counted into"
            ),
            "qualifying_streams": ["gas", "oil"],
            "excluded_streams": ["water"],
            "liquids_basis": "oil+condensate",
        },
        "code_ref": POLICY_READER,
        "rule": "Oil and gas qualify; water alone never does. ND oil is oil plus condensate.",
        "rationale": (
            "The ask named Gas/Oil/Water, and water is the one that has to be argued about."
            " Water is a byproduct: a well lifting water and no hydrocarbon is not producing in"
            " any sense an analyst means, and admitting it would sweep in the injection and"
            " disposal population, which is exactly the set the well_type rule exists to keep"
            " separate. The cost of excluding it is measured, not assumed - on the 2026-08-23"
            " load 9 of 20,643 active wells have positive water and no positive oil or gas in"
            " any month, so the decision moves 9 wells and buys a class that means what it"
            " says. Condensate is not a separate ND stream: cr_nd_liquids_policy_1 records that"
            " ND liquids are oil plus condensate, so the oil column already carries it and the"
            " basis is restated on every surface that serves one of these counts. Water is"
            " still promoted, still served and still charted; it is not evidence of producing."
        ),
        "evidence_url": MPR_FILE_URL,
        "effective_from": PRODUCING_FROM,
    },
    {
        "rule_id": "cr_producing_evidence_1",
        "source_id": "nd_mpr_xlsx",
        "stage": "conform",
        "rule_kind": "code_ref",
        "applies_to_fields": ["null_semantics", "volume"],
        "spec": {
            "module_function": POLICY_READER,
            "version": "1",
            "contract_note": (
                "returns qualifying_null_semantics; the classifier reads the newest vintage of"
                " each month and stream, and answers unknown where it has no filing to read"
            ),
            "qualifying_null_semantics": ["reported"],
            "min_volume_exclusive": "0",
            "classes": ["producing", "not_producing", "unknown"],
            "absent_is_unknown": True,
            "withheld_is_unknown": True,
            "lease_reported_is_unknown": True,
        },
        "code_ref": POLICY_READER,
        "rule": "Only a filed positive volume proves producing; an absent filing proves nothing.",
        "rationale": (
            "cr_nd_null_semantics_1 already holds that a filed zero, an absent report and a"
            " withheld one are three different facts, and this rule is what stops the producing"
            " question collapsing them back together. A reported_zero row is the regulator"
            " saying the well produced nothing, and on this load the two are cleanly separated:"
            " every one of the 1,082,374 reported_zero rows carries volume 0 and none of the"
            " 6,141,170 reported rows does. So a well with filings in the window but no"
            " positive hydrocarbon month is not_producing - a fact - while a well with no"
            " filing at all in the window is unknown, an absence. Treating the second as the"
            " first would report an absence of evidence as evidence of absence for 1,226 of the"
            " active wells alone. Withheld is unknown for the same reason and with a sharper"
            " edge: 4,368 wells have production quarantined as confidential_withheld, so their"
            " months never reach canonical, and 942 of the 968 wells currently carrying the"
            " confidential status have no filing here at all. They are wells whose numbers are"
            " held back, not wells that stopped. A jurisdiction reporting at the lease is"
            " unknown on the same principle (DIR-3, cr_tx_allocation_scope_1): Texas has no"
            " well-level series at all, so answering not_producing there would misreport all"
            " 114,122 wells the state calls active. Restatements are read at their newest"
            " vintage, never their first (DIR-2). Note that stream_not_promoted is not evidence"
            " of anything here - all 5,052,644 of those rows are the GasSold and Flared"
            " disposition columns, which are not streams."
        ),
        "evidence_url": MPR_FILE_URL,
        "effective_from": PRODUCING_FROM,
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
        "effective_from": rule.get("effective_from", PRODUCING_FROM),
    }


def seed_conformance_producing(connection: psycopg.Connection) -> int:
    """Counted by family, not by source: these rows share nd_mpr_xlsx with the ND registry,
    and a source-wide count here would move whenever that registry grew."""
    with connection.cursor() as cursor:
        cursor.executemany(_INSERT, [_row(rule) for rule in PRODUCING_RULES])
        cursor.execute(
            "select count(*) from lineage.conformance_rules where rule_family like 'cr\\_%%'"
            " and rule_id = any(%s)",
            ([str(rule["rule_id"]) for rule in PRODUCING_RULES],),
        )
        return int(cursor.fetchone()[0])
