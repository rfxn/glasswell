"""The PDQ dump is a registered source before anything tries to fetch it.

A unit assertion on purpose: `tests/conftest.py`'s FIXTURE_SOURCES already inserts a
`tx_pdq_dsv` row into every test database, so an integration test asserting the row exists
would pass against the fixture whether or not the seeder carries it.
"""

from __future__ import annotations

from glasswell.seed.conformance_tx import TX_SOURCES, seed_conformance_tx


def test_the_pdq_dump_is_registered_as_a_texas_source() -> None:
    row = next(source for source in TX_SOURCES if source["source_id"] == "tx_pdq_dsv")

    assert row["jurisdiction"] == "TX"
    assert row["redistributable"] is False
    assert "PDQ_DSV.zip" in str(row["name"])


def test_the_pdq_dump_carries_the_jurisdiction_licence_note() -> None:
    """The downloads index states the files are free and imposes no redistribution clause; the
    note is the one every TX source already carries, not a second wording beside it."""
    rows = {str(source["source_id"]): source for source in TX_SOURCES}

    assert rows["tx_pdq_dsv"]["license_note"] == rows["tx_wellbore_ewa_csv"]["license_note"]


def test_the_sources_are_seeded_before_the_rules_that_cite_them() -> None:
    """A rule row cannot be sourceless (005_conformance.sql:7), so the ordering is the
    seeder's contract rather than a convention a reader has to notice."""
    names = seed_conformance_tx.__code__.co_names

    assert names.index("seed_sources_tx") < names.index("_INSERT_RULE")
