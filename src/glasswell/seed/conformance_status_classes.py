"""The decisions the canonical status class domain rests on (R8).

Three rules and no fourth. The domain names the eleven mapped classes, their order and their
symbology; the absence basis says what the twelfth class means and how a consumer tells its two
cases apart; the absence share says how much of a jurisdiction's spine may legitimately resolve
to it, which `infra/verify.sh` reads rather than carrying a threshold of its own.

No regulator code appears in any of them. Which codes reach a class is the per-jurisdiction
mapping rule's fact and resolves at /conformance/{rule_id}.
"""

from __future__ import annotations

from datetime import date

import psycopg
from psycopg.types.json import Jsonb

# Valid time: the release these decisions are published in. The integrator repoints it beside
# seed/status_classes.py's DOMAIN_EFFECTIVE_FROM, per the migration's REPOINT CHECKLIST.
EFFECTIVE_FROM = date(2026, 9, 6)

CLASS_DOMAIN_RULE_ID = "cr_status_class_domain_1"
ABSENCE_BASIS_RULE_ID = "cr_status_absence_basis_1"
ABSENCE_SHARE_RULE_ID = "cr_status_absence_share_1"

STATUS_CLASS_RULE_IDS = (CLASS_DOMAIN_RULE_ID, ABSENCE_BASIS_RULE_ID, ABSENCE_SHARE_RULE_ID)

DOMAIN_TABLE = "lineage.status_classes"

# The eleven mapped ids in sort_order. Spelled here as the decision's own content: a rule that
# named no classes would be a published decision a reader cannot check.
MAPPED_CLASSES = (
    "active",
    "drilling",
    "confidential",
    "permitted",
    "inactive",
    "temporarily_abandoned",
    "service",
    "plugged",
    "dry",
    "documented_unmapped",
    "expired",
)

# The highest legitimate absence share measured on the deployed spine: Texas, 68,186 of 359,421
# wells_latest rows on 2026-09-03. The ceiling is set above it with room for a load, because a
# threshold at the measurement would go red on the next Texas county.
MAX_ABSENCE_SHARE = 0.30

# The source column is not null and every cross-cutting decision in the tree is filed under the
# founding source, as cr_producing_* and cr_tc_* already are: eight rows deep, and none of them
# a North Dakota fact. It is the rule's filing anchor and not a claim that the domain belongs to
# one regulator, and `source_is_filing_anchor` is what lets a reader and a gate tell the two
# apart. Whether lineage.sources should carry a shape for a decision that interprets no
# publication is the registry track's question, not this one's.
SOURCE_ID = "nd_mpr_xlsx"
FILING_ANCHOR = True

# The three the bar does not hold for, with the substrates they fail on, published beside the
# bar itself: a reader resolving this rule was told the domain clears 3:1 against four
# backgrounds, and for three of twelve classes on the light theme that is false. Every one of
# these colours is byte-identical to what shipped before this track, so they are carried
# forward rather than caused here, and the palette question is routed to BRAND.md.
CONTRAST_EXCEPTIONS: dict[str, list[str]] = {
    "active": ["light map"],
    "confidential": ["light panel", "light map"],
    "permitted": ["light panel", "light map"],
}
CONTRAST_EXCEPTIONS_ROUTED_TO = "BRAND.md"

STATUS_CLASS_RULES: tuple[dict[str, object], ...] = (
    {
        "rule_id": CLASS_DOMAIN_RULE_ID,
        "source_id": SOURCE_ID,
        "stage": "conform",
        "rule_kind": "code_ref",
        "applies_to_fields": ["status_canonical"],
        "spec": {
            "classes": list(MAPPED_CLASSES),
            "absence_class_rule": ABSENCE_BASIS_RULE_ID,
            "symbology_source": DOMAIN_TABLE,
            # The two theme panels and the two map substrates a swatch is read against. A
            # colour is a served datum, so the bar it has to clear is one too.
            "min_contrast_ratio": 3.0,
            "contrast_measured_against": ["#121A21", "#0E151B", "#FFFFFF", "#F2F5F8"],
            "min_contrast_exceptions": dict(CONTRAST_EXCEPTIONS),
            "min_contrast_exceptions_routed_to": CONTRAST_EXCEPTIONS_ROUTED_TO,
            "module_function": "glasswell.lineage.status_classes:load_status_classes",
            "source_is_filing_anchor": FILING_ANCHOR,
            "contract_note": (
                "a declaration the serving path reads, not a frame transformation: the domain"
                " is rows and the foreign keys are what enforce it"
            ),
            "superseded_by_action": "a new rule and a single-transaction repoint of every map"
            " that names a withdrawn class",
        },
        "code_ref": "glasswell.lineage.status_classes:load_status_classes",
        "rule": "The eleven mapped canonical well-status classes, their legend order and their"
        " symbology are the rows of lineage.status_classes; every registered status map targets"
        " that set through a foreign key.",
        "rationale": (
            "The domain existed in three places that agreed only by coincidence: a union over"
            " five per-regulator maps computed at query time, a prose enumeration in the"
            " glossary, and a closed array of object literals in the client. None was checked"
            " against another, so the day a regulator's map gained a class the client had never"
            " heard of, that class would have been painted, counted and filtered as the absence"
            " class and would have vanished the moment a reader unticked one box. Making the"
            " domain rows makes it a decision with a rationale and an effective date, which is"
            " what R8 requires of the mapping that targets it, and makes the foreign key the"
            " single writer rather than a second list. Presentation travels with the class"
            " because presentation is what a client needs served: an enum carries a name and"
            " nothing else, and a colour with no row behind it is a symbology decision no gate"
            " can read. Two of the twelve are repainted rather than carried across, and the bar"
            " is part of the decision so the next class has one to clear: a swatch is a"
            " non-text mark, so 3:1 is its floor, and it is read against both theme panels and"
            " both map substrates. The values carried across measured 2.19:1 for the absence"
            " class and 2.94:1 for expired against the dark panel, which is the substrate the"
            " app opens on; the absence class was the least legible mark on a canvas this same"
            " decision turns it into a first-class row of."
            " Three of the twelve do not clear it on the light theme and are named in"
            " min_contrast_exceptions with the substrates they fail on rather than left to a"
            " reader to discover: active on the light map, confidential and permitted on both"
            " light substrates. Every one of those values is byte-identical to what shipped"
            " before this decision, so they are carried forward rather than caused by it, and"
            " the palette question they raise is routed to BRAND.md."
        ),
        "evidence_url": "https://glasswell.rpx.sh/conformance",
    },
    {
        "rule_id": ABSENCE_BASIS_RULE_ID,
        "source_id": SOURCE_ID,
        "stage": "conform",
        "rule_kind": "code_ref",
        "applies_to_fields": ["status_canonical", "status_reported"],
        "spec": {
            "served_class": "unmapped",
            "distinguished_by": "status_reported",
            "filed_code_present_means": "the registered vocabulary has no row for this code",
            "filed_code_absent_means": "the source filed no status",
            "module_function": "glasswell.status_resolution:resolved_status",
            "source_is_filing_anchor": FILING_ANCHOR,
            "contract_note": (
                "read at query-assembly time by the one helper every serving path calls, so"
                " the tile, the facet, the filter, the count and the card change together"
            ),
        },
        "code_ref": "glasswell.status_resolution:resolved_status",
        "rule": "No serving path emits a null status class. Where neither the promotion nor the"
        " registry resolves one, the absence class is served and the filed code beside it is"
        " what says which of the two cases holds.",
        "rationale": (
            "Null is indistinguishable from not-yet-loaded to every consumer, which is why the"
            " blueprint forbids serving it, and it has been served anyway for every well whose"
            " source filed no status code at all. The absence class is a class: it draws, it"
            " counts, it filters and it carries a note. What it is not is a claim about why,"
            " and that is the reason the two cases are distinguished by the reported code"
            " rather than by two classes. A second class for a filed-but-unmapped code would"
            " mint a vocabulary entry for a fact the registered mapping rule already answers."
        ),
        "evidence_url": "https://glasswell.rpx.sh/conformance",
    },
    {
        "rule_id": ABSENCE_SHARE_RULE_ID,
        "source_id": SOURCE_ID,
        "stage": "conform",
        "rule_kind": "code_ref",
        "applies_to_fields": ["status_canonical"],
        "spec": {
            "scope": "per_jurisdiction",
            "max_share": MAX_ABSENCE_SHARE,
            "measured_on": "canonical.wells_latest",
            "module_function": "glasswell.lineage.status_classes:absence_share_ceiling",
            "source_is_filing_anchor": FILING_ANCHOR,
            "contract_note": (
                "an operational ceiling read by infra/verify.sh V-3 through that symbol, and"
                " by nothing on the wire: it is a property of a deployment, not of a class"
            ),
        },
        "code_ref": "glasswell.lineage.status_classes:absence_share_ceiling",
        "rule": "No jurisdiction may serve the absence class for more than the registered share"
        " of its resident wells.",
        "rationale": (
            "Serving a class for every well removes the null that used to make a failed"
            " resolver visible, so the threshold is the replacement signal and it has to be a"
            " published decision rather than a literal in a shell script. The highest"
            " legitimate share measured on the deployed spine is 19.0 per cent, 68,186 of"
            " 359,421 Texas wells_latest rows on 2026-09-03, every one of which filed no status"
            " code at all. The ceiling sits above that with room for a load rather than at it,"
            " because a threshold set at the measurement reddens on the next county rather than"
            " on the fault it exists to catch."
        ),
        "evidence_url": "https://glasswell.rpx.sh/conformance",
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


def seed_conformance_status_classes(connection: psycopg.Connection) -> int:
    """Rule ids are immutable: a change is a new row with supersedes_rule_id."""
    with connection.cursor() as cursor:
        cursor.executemany(_INSERT, [_row(rule) for rule in STATUS_CLASS_RULES])
        cursor.execute(
            "select count(*) from lineage.conformance_rules where rule_id = any(%s)",
            (list(STATUS_CLASS_RULE_IDS),),
        )
        return int(cursor.fetchone()[0])
