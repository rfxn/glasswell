"""Which clock a well header's `effective_from` is, per jurisdiction, as a row (R8).

A status history is only a history where the date beside a filed code is the regulator's own
valid time. Where it is the load stamp glasswell wrote when it pulled, a "history" would be a
log of when glasswell looked, and an empty one would read as "this well never changed" rather
than as "no history was ever captured here". Consumers cannot tell those two apart from an
empty list, which is why the distinction is a rule and why `links.history` is emitted from it
and from nothing else.

One row per jurisdiction whose header carries a source valid time, each filed under that
jurisdiction's own source with that jurisdiction's own evidence: a Colorado reader following
`links.history_rule` was shown New Mexico's OCD archive as the evidence for a decision about
Colorado's clock, which is R8's own failure mode. The registry decides who each answers for,
so a fifth jurisdiction joins by registering a row rather than by a code change.
"""

from __future__ import annotations

from datetime import date

import psycopg
from psycopg.types.json import Jsonb

from glasswell.seed.conformance_co import (
    WELLS_METADATA_URL as CO_WELLS_METADATA_URL,
)
from glasswell.seed.conformance_co import (
    WELLS_SOURCE_ID as CO_WELLS_SOURCE_ID,
)

STATUS_HISTORY = "status_history"

NM_HISTORY_RULE_ID = "cr_nm_wellhistory_status_history_1"
CO_HISTORY_RULE_ID = "cr_co_wells_status_history_1"
HISTORY_RULE_IDS = (NM_HISTORY_RULE_ID, CO_HISTORY_RULE_ID)

# The two classes an `effective_from` can belong to, and the whole of the decision.
SOURCE_VALID_TIME = "source_valid_time"
LOAD_STAMP = "load_stamp"

HISTORY_FROM = date(2026, 9, 3)

# Measured on the deployed spine on 2026-09-02 with
#   select left(api10,2), count(distinct effective_from), min(effective_from),
#          max(effective_from) from canonical.wells group by 1
# and the changed-code counts with a `having count(distinct status_reported) > 1` grouping.
CLOCKS: dict[str, dict[str, object]] = {
    "ND": {
        "clock": LOAD_STAMP,
        "effective_from_is": "the vintage of the workbook the header was promoted from",
        "distinct_effective_dates": 2,
        "wells_with_a_changed_filed_code": 0,
        "effective_rule": "cr_nd_status_vocab_1",
    },
    "MT": {
        "clock": LOAD_STAMP,
        "effective_from_is": "the vintage of the GIS extract the header was promoted from",
        "distinct_effective_dates": 1,
        "wells_with_a_changed_filed_code": 0,
        "effective_rule": "cr_mt_gis_status_vocab_1",
    },
    "TX": {
        "clock": LOAD_STAMP,
        "effective_from_is": "the vintage of the wellbore extract the header was promoted from",
        "distinct_effective_dates": 1,
        "wells_with_a_changed_filed_code": 0,
        "effective_rule": "cr_tx_status_vocab_1",
    },
    "NM": {
        "clock": SOURCE_VALID_TIME,
        "effective_from_is": "eff_dte, the date OCD stamped the header it filed",
        "distinct_effective_dates": 15590,
        "wells_with_a_changed_filed_code": 31707,
        "effective_rule": "cr_nm_wellhistory_effective_1",
    },
    "CO": {
        "clock": SOURCE_VALID_TIME,
        "effective_from_is": "Stat_Date, the date ECMC stamped the status it filed",
        "distinct_effective_dates": None,
        "wells_with_a_changed_filed_code": None,
        "effective_rule": "cr_co_wells_effective_1",
    },
}

REGISTERS = tuple(
    code for code, clock in CLOCKS.items() if clock["clock"] == SOURCE_VALID_TIME
)

# What every jurisdiction's row says the same way, so the two cannot drift into two answers
# about the same serving path.
_SHARED_SPEC: dict[str, object] = {
    "decision": STATUS_HISTORY,
    "module_function": "glasswell.api.routers.wells:get_well_status_history",
    "version": "1",
    "contract_note": (
        "reads the registry for the status_history decision and serves a history only"
        " where one is registered; the class column is resolved through"
        " glasswell.status_resolution and never mapped in the router"
    ),
    "axis": "status_reported",
    "not_the_axis": "status_canonical",
    "why_not_the_canonical_class": (
        "A canonical class is glasswell's own mapping decision and can be superseded"
        " by a rule. A history over it would show a rule edit as if the regulator had"
        " changed its mind, and it would be empty everywhere: zero wells in the spine"
        " carry more than one distinct status_canonical."
    ),
    "class_column_label": "class as glasswell maps this code today",
    "class_column_is_historical": False,
    "class_column_resolver": "glasswell.status_resolution:resolver_join",
    "cap": 10,
    "order": "effective_from desc",
    "clocks": CLOCKS,
    "registers_for": list(REGISTERS),
    "emits": "links.history",
    "measured_on": "2026-09-03",
    "measured": {
        "wells_whose_status_canonical_ever_changes": 0,
        "wells_whose_status_reported_ever_changes": 31707,
        "wells_with_more_than_one_effective_row": {"NM": 80294, "ND": 43817},
        "distinct_effective_dates": {"NM": 15590, "ND": 2, "MT": 1, "TX": 1},
        "headers_on_the_fullest_single_well": {"NM": 15, "ND": 2, "MT": 1, "TX": 1},
        "nm_effective_range": ["1900-01-01", "2026-08-19"],
    },
    "successor": (
        "v0.81 resolves each historical row under the rule in force at that row's"
        " knowledge time, which resolver_join already takes a date for and the"
        " registry's second clock already supports. Until then the class column is"
        " labelled rather than claimed."
    ),
}

_RULE_TEXT = (
    "A well header's status history is served over the filed code and only where the"
    " jurisdiction's effective_from is the regulator's own valid time. Where it is the"
    " load stamp glasswell wrote when it pulled, no history is served and the absence"
    " is stated rather than left as an empty list."
)

# The half that is the same wherever the decision is registered: what the class column is, and
# why it is labelled rather than claimed.
_CLASS_COLUMN_RATIONALE = (
    " The class column is the second decision here and it is labelled rather than"
    " claimed. It is a read-time join against today's registry through the one shared"
    " resolver, so when a vocabulary rule is superseded every historical row changes"
    " class at once with nothing on screen saying the regulator did not move. The"
    " column header says 'class as glasswell maps this code today', each row carries"
    " the mapping rule id that produced it, and resolution under the rule clock is"
    " scheduled rather than declined."
)

_SHARED_MEASUREMENT = (
    "Measured on the deployed spine on 2026-09-03. Zero of 585,864 wells carry more than one"
    " distinct status_canonical, so a canonical timeline would render empty for every well in"
    " the system; 31,707 wells carry a changed status_reported and every one of them is in New"
    " Mexico. The three load-stamp jurisdictions serve the absence with their own"
    " status_vocabulary rule beside it, and each of them says so by name."
)


def _history_rule(
    rule_id: str, *, source_id: str, evidence_url: str, rationale: str
) -> dict[str, object]:
    return {
        "rule_id": rule_id,
        "source_id": source_id,
        "stage": "conform",
        "rule_kind": "code_ref",
        "applies_to_fields": ["effective_from", "status_reported"],
        "spec": dict(_SHARED_SPEC),
        "code_ref": "glasswell.api.routers.wells:get_well_status_history",
        "rule": _RULE_TEXT,
        "rationale": rationale,
        "evidence_url": evidence_url,
        "effective_from": HISTORY_FROM,
    }


# One per jurisdiction rather than one shared row: the rule id names the table its source holds
# (P3.0's convention, which cr_status_history_basis_1 broke), and a reader who follows a
# Colorado card's links.history_rule is shown ECMC's evidence rather than New Mexico's.
HISTORY_RULES: tuple[dict[str, object], ...] = (
    _history_rule(
        NM_HISTORY_RULE_ID,
        source_id="nm_ocd_wellhistory",
        evidence_url="https://ocdimage.emnrd.nm.gov/imaging/OCDPermitsData/wellhistory.zip",
        rationale=(
            f"{_SHARED_MEASUREMENT} New Mexico's header clock is a source valid time:"
            " cr_nm_wellhistory_effective_1 promotes eff_dte, the date OCD stamped the header"
            " it filed, and the population holds 15,590 distinct effective_from values"
            " spanning 1900-01-01 to 2026-08-19 against North Dakota's two, Montana's one and"
            " Texas's one. The fullest single well carries 15 of them, which is why the"
            " response caps at ten and counts the remainder rather than paging."
            f"{_CLASS_COLUMN_RATIONALE}"
        ),
    ),
    _history_rule(
        CO_HISTORY_RULE_ID,
        source_id=CO_WELLS_SOURCE_ID,
        evidence_url=CO_WELLS_METADATA_URL,
        rationale=(
            f"{_SHARED_MEASUREMENT} Colorado registers the same shape without yet holding"
            " wells in the spine: cr_co_wells_effective_1 promotes Stat_Date, the date ECMC"
            " stamped the status it filed, and states in its own rationale that keying on the"
            " pull would append 124,392 rows a night and make the spine a log of when"
            " glasswell looked. The measurement of how many headers a Colorado well carries"
            " waits on the wells landing; the clock is registered now, so the section exists"
            " the day they do."
            f"{_CLASS_COLUMN_RATIONALE}"
        ),
    ),
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
        "effective_from": rule.get("effective_from", HISTORY_FROM),
    }


def seed_conformance_status_history(connection: psycopg.Connection) -> int:
    """The rule itself. Its registration is declared in `seed.jurisdictions.JURISDICTION_RULES`
    and written by `seed_jurisdictions`, which is the one writer the parity gate reads: a
    registry row this module planted directly would be resident and undeclared, and
    test_jurisdiction_parity refuses exactly that. Counted over its own ids."""
    rule_ids = [str(rule["rule_id"]) for rule in HISTORY_RULES]
    with connection.cursor() as cursor:
        cursor.executemany(_INSERT, [_row(rule) for rule in HISTORY_RULES])
        cursor.execute(
            "select count(*) from lineage.conformance_rules where rule_id = any(%s)",
            (rule_ids,),
        )
        return int(cursor.fetchone()[0])
