from __future__ import annotations

import pytest

from glasswell.seed.glossary import load_glossary_seed, slug

TERMS = load_glossary_seed()
MINIMUM_TERMS = 30

# M7: ordinary words a well card repeats. Reachable by click, never auto-scanned.
STOPWORDS = (
    "Band",
    "Analog",
    "Wellbore",
    "Withheld",
    "Water cut",
    "Vintage (well vintage)",
    "Stream",
    "Slot",
    "Spine",
)

# SB-07 §12 hands these back to SB-00 as undefined; they are what the drawer surfaces.
SPINE_TERMS = (
    "Derivation handle",
    "Manifest",
    "Recipe",
    "Vintage (well vintage)",
    "Valid time",
    "Knowledge time",
    "Quarantine",
    "Audit stream",
    "Determinism class",
    "Naked number",
)


def entry(term: str) -> dict:
    return next(row for row in TERMS if row["term"] == term)


def test_the_seed_carries_at_least_the_cut_line_floor():
    assert len(TERMS) >= MINIMUM_TERMS


@pytest.mark.parametrize("field", ["term", "short_definition", "expanded_definition"])
def test_every_entry_carries_the_required_prose(field):
    missing = [row.get("term") for row in TERMS if not str(row.get(field, "")).strip()]
    assert missing == []


def test_every_entry_carries_at_least_one_domain_tag():
    untagged = [row["term"] for row in TERMS if not row.get("domain_tags")]
    assert untagged == []


def test_every_entry_cites_where_it_came_from():
    uncited = [row["term"] for row in TERMS if not row.get("source_refs")]
    assert uncited == []


def test_terms_are_unique_case_insensitively():
    folded = [row["term"].lower() for row in TERMS]
    assert sorted(folded) == sorted(set(folded))


def test_the_lineage_terms_sb07_records_as_undefined_are_all_seeded():
    seeded = {row["term"] for row in TERMS}
    assert set(SPINE_TERMS) - seeded == set()


def test_a_related_term_always_resolves_to_another_seeded_term():
    reachable = {row["term"].lower() for row in TERMS}
    reachable |= {alias.lower() for row in TERMS for alias in row.get("aliases") or ()}
    dangling = {
        (row["term"], related)
        for row in TERMS
        for related in row.get("related_terms") or ()
        if related.lower() not in reachable
    }
    assert dangling == set()


def test_the_words_a_well_card_repeats_are_not_auto_highlighted():
    assert [term for term in STOPWORDS if entry(term).get("highlightable", True)] == []


def test_terms_the_drawer_must_highlight_stay_highlightable():
    assert entry("Derivation handle")["highlightable"] is True
    assert entry("Report vintage")["highlightable"] is True


def test_the_audit_stream_entry_does_not_claim_the_hash_chain_that_was_cut():
    audit = entry("Audit stream")
    prose = f"{audit['short_definition']} {audit['expanded_definition']}".lower()
    assert "hash-chain" not in prose
    assert "hash chain" not in prose
    assert "trigger" in prose


def test_no_entry_reintroduces_the_retired_support_score_name():
    offenders = [
        row["term"]
        for row in TERMS
        if "support score" in f"{row['term']} {row['short_definition']}".lower()
    ]
    assert offenders == []


@pytest.mark.parametrize(
    ("term", "expected"),
    [
        ("Bitemporal", "bitemporal"),
        ("Report vintage", "report_vintage"),
        ("API-10 / API-12 / API-14", "api_10_api_12_api_14"),
        ("Cum12 / cum24", "cum12_cum24"),
    ],
)
def test_slug_is_lowercase_and_identifier_safe(term, expected):
    assert slug(term) == expected


def test_every_seeded_term_slugs_to_a_distinct_id():
    ids = [slug(row["term"]) for row in TERMS]
    assert sorted(ids) == sorted(set(ids))
