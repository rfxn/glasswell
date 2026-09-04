"""The canonical status class domain as rows: the twelve the migration ships, mirrored.

Two writers for the reason `seed/jurisdictions.py` gives: the migration carries the rows so a
migrated database serves, and `seed_all` re-asserts them on every deploy so a class appended in
a later release without a migration of its own still lands.
`tests/contract/test_status_class_parity.py` holds the two copies, and the wire, to each other.
"""

from __future__ import annotations

from datetime import date

import psycopg

from glasswell.seed.conformance_status_classes import (
    ABSENCE_BASIS_RULE_ID,
    CLASS_DOMAIN_RULE_ID,
    STATUS_CLASS_RULE_IDS,
    seed_conformance_status_classes,
)
from glasswell.status_resolution import UNMAPPED_CLASS

# Valid time and knowledge time of the domain, which are one date: a class that stops existing
# has to be repointed in every map that names it inside one transaction, so a supersession here
# is not resolvable and there is nothing for a second clock to answer. The two clocks the
# decision does carry live on cr_status_class_domain_1 through conformance_rule_publications.
# The integrator repoints this beside the evidence pair, per the migration's REPOINT CHECKLIST.
DOMAIN_EFFECTIVE_FROM = date(2026, 9, 3)
DOMAIN_EVIDENCE_TAG = "UNRELEASED"
# Spelled out rather than computed: release.py scans this file for the quoted placeholder, and
# an expression that evaluates to it is invisible to that scan.
DOMAIN_EVIDENCE_COMMIT = "0000000000000000000000000000000000000000"

# The eleven mapped classes and the one absence class, in legend order. Every label, glyph and
# min_zoom is carried across verbatim from what the canvas already draws. Two things are
# deliberate changes: the notes name no regulator and no regulator code, because which codes
# reach a class is the per-jurisdiction mapping rule's fact; and `expired` and `unmapped` are
# repainted, because the values carried across measured 2.94:1 and 2.19:1 against the dark
# panel and the absence class is the one this train turns from a negation nobody could tick
# into a row drawn on five jurisdictions with a count on every box. Every class now clears
# 3:1 against both themes' panels and both map substrates; see the domain rule's rationale.
STATUS_CLASSES: tuple[dict[str, object], ...] = (
    {
        "status_canonical": "active",
        "label": "Active",
        "colour": "#3FA55E",
        "glyph": "solid",
        "min_zoom": 4,
        "sort_order": 10,
        "note": "Producing, or filed as capable of production.",
    },
    {
        "status_canonical": "drilling",
        "label": "Drilling",
        "colour": "#3D8BD4",
        "glyph": "bar",
        "min_zoom": 4,
        "sort_order": 20,
        "note": "Spudded and not yet filed as completed.",
    },
    {
        "status_canonical": "confidential",
        "label": "Confidential",
        "colour": "#E4A33C",
        "glyph": "solid",
        "min_zoom": 6,
        "sort_order": 30,
        "note": "Withheld under an operator's tight-hole election: a status, not missing data.",
    },
    {
        "status_canonical": "permitted",
        "label": "Permitted",
        "colour": "#9FB0BC",
        "glyph": "hollow",
        "min_zoom": 6,
        "sort_order": 40,
        "note": "An approved location with no wellbore filed yet.",
    },
    {
        "status_canonical": "inactive",
        "label": "Inactive",
        "colour": "#D9534F",
        "glyph": "bar",
        "min_zoom": 8,
        "sort_order": 50,
        "note": "Shut in, or carrying an inactive-well waiver.",
    },
    {
        "status_canonical": "temporarily_abandoned",
        "label": "Temporarily abandoned",
        "colour": "#D9534F",
        "glyph": "dashed",
        "min_zoom": 8,
        "sort_order": 60,
        "note": "Suspended and not plugged.",
    },
    {
        "status_canonical": "service",
        "label": "Service",
        "colour": "#7A6FD0",
        "glyph": "hollow",
        "min_zoom": 8,
        "sort_order": 70,
        "note": "Injection, disposal, storage, observation or water supply, not a producer.",
    },
    {
        "status_canonical": "plugged",
        "label": "Plugged & abandoned",
        "colour": "#7C8B96",
        "glyph": "struck",
        "min_zoom": 9,
        "sort_order": 80,
        "note": "The wellbore is permanently plugged.",
    },
    {
        "status_canonical": "dry",
        "label": "Dry hole",
        "colour": "#7C8B96",
        "glyph": "struck-hollow",
        "min_zoom": 9,
        "sort_order": 90,
        "note": "Drilled with no commercial completion filed.",
    },
    {
        "status_canonical": "documented_unmapped",
        "label": "Documented, no class",
        "colour": "#8E6E9E",
        "glyph": "hollow",
        "min_zoom": 9,
        "sort_order": 100,
        "note": "The regulator publishes this code and glasswell has no equivalent class, so"
        " the filed code is served instead of a guess.",
    },
    {
        "status_canonical": "expired",
        "label": "Expired permit",
        "colour": "#4A7480",
        "glyph": "dashed",
        "min_zoom": 9,
        "sort_order": 110,
        "note": "A permit lapsed, was cancelled or was vacated before spud, so no wellbore"
        " exists.",
    },
    {
        # min_zoom 0: absence must not be the thing that hides, which is the argument the
        # canvas already made and which is data here so a reader can find it.
        "status_canonical": UNMAPPED_CLASS,
        "label": "Unmapped status",
        "colour": "#666A71",
        "glyph": "hollow",
        "min_zoom": 0,
        "sort_order": 120,
        "is_absence": True,
        "rule_id": ABSENCE_BASIS_RULE_ID,
        "note": "No class resolved. Either the source filed no status, or it filed a code its"
        " registered vocabulary has no row for; the well card and the hover say which, because"
        " they carry the filed code.",
    },
)

DOMAIN_RATIONALE = (
    "The class domain is a decision with a rationale and an effective date, not the union of"
    " five per-regulator maps computed at runtime. Every mapping targets this set through a"
    " foreign key, so a class outside it is a mapping with no published decision behind it."
)

_INSERT_PUBLICATION = """
insert into lineage.conformance_rule_publications
    (rule_id, published_vintage, evidence_tag, evidence_commit)
values (%(rule_id)s, %(published_vintage)s, %(evidence_tag)s, %(evidence_commit)s)
on conflict (rule_id) do nothing
"""

# Guarded on rule residency exactly as the migration is: a class with no published decision
# behind it is the failure the domain exists to prevent, so the row waits for its rule.
_INSERT_CLASS = """
insert into lineage.status_classes
    (status_canonical, label, colour, glyph, min_zoom, sort_order, note, is_absence, rule_id,
     effective_from, published_at, rationale)
select %(status_canonical)s, %(label)s, %(colour)s, %(glyph)s, %(min_zoom)s, %(sort_order)s,
       %(note)s, %(is_absence)s, %(rule_id)s, %(effective_from)s, %(published_at)s,
       %(rationale)s
 where exists (select 1 from lineage.conformance_rules where rule_id = %(rule_id)s)
on conflict do nothing
"""


def class_parameters(row: dict[str, object]) -> dict[str, object]:
    """One domain row with its clock, its rule and its defaults resolved."""
    return {
        "is_absence": False,
        "rule_id": CLASS_DOMAIN_RULE_ID,
        **row,
        "effective_from": DOMAIN_EFFECTIVE_FROM,
        "published_at": DOMAIN_EFFECTIVE_FROM,
        "rationale": DOMAIN_RATIONALE,
    }


def publication_parameters(rule_id: str) -> dict[str, object]:
    return {
        "rule_id": rule_id,
        "published_vintage": DOMAIN_EFFECTIVE_FROM,
        "evidence_tag": DOMAIN_EVIDENCE_TAG,
        "evidence_commit": DOMAIN_EVIDENCE_COMMIT,
    }


def seed_status_classes(connection: psycopg.Connection) -> int:
    """Idempotent by contract: seed_all runs it on every deploy. Returns the domain size.

    Three writes in one order, because each refuses without the one before it: 049's trigger
    refuses a conformance rule with no published vintage, and the domain rows carry a foreign
    key to the rule that declared them.
    """
    with connection.cursor() as cursor:
        cursor.executemany(
            _INSERT_PUBLICATION,
            [publication_parameters(rule_id) for rule_id in STATUS_CLASS_RULE_IDS],
        )
    seed_conformance_status_classes(connection)
    with connection.cursor() as cursor:
        cursor.executemany(_INSERT_CLASS, [class_parameters(row) for row in STATUS_CLASSES])
        # The five map foreign keys and the resolver's. A constraint cannot point at a domain
        # that is not resident, and on a fresh database the migration runs before this seeder,
        # so the migration's own call is a no-op there and this one is what lands them.
        cursor.execute("select lineage.attach_status_class_constraints()")
        cursor.execute("select count(*) from lineage.status_classes")
        return int(cursor.fetchone()[0])
