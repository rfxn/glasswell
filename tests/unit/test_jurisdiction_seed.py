"""The registry's own data, held to the things no database constraint can see.

The registrations ship on two paths -- the migration and `seed/jurisdictions.py` -- and the
database gate that holds the two together needs docker. These are the ones that do not: that
the two paths agree about the repoint, that every declared tile layer and colour exists, and
that each registration carries the decision no jurisdiction may be without.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pytest

import glasswell.seed.jurisdictions as mirror
from glasswell.db.migrate import discover_migrations
from glasswell.marts.tiles import TILE_LAYERS
from glasswell.seed.jurisdictions import (
    CODES,
    EVIDENCE_COMMIT,
    JURISDICTION_CODES,
    JURISDICTION_RESTATEMENTS,
    JURISDICTION_RULES,
    JURISDICTION_RULES_AS_FOUNDED,
    JURISDICTIONS,
    NAMES,
    PREFIXES,
    PRESENTATION_COLUMNS,
    REQUIRED_DECISIONS,
    RESTATED_EVIDENCE_COMMIT,
    RESTATED_EVIDENCE_TAG,
    identity_pattern,
    rule_parameters,
)
from glasswell.status_resolution import UNMAPPED_CLASS

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
# By name, never by number: a migration number is assigned by merge order and this one has
# already moved twice.
MIGRATION = next(
    item.path for item in discover_migrations() if item.name == "jurisdictions"
)
BRAND = ROOT / "BRAND.md"
STATUS_CLASSES = ROOT / "web/src/map/status.ts"
REPOINTED_COMMIT = re.compile(r"^[0-9a-f]{40}$")
ABSENCE_CLASS = re.compile(
    r"export const UNMAPPED_STATUS: StatusClass = \{\s*id: \"([a-z_]+)\",", re.S
)


def repoint_disagreements(migration: str) -> list[str]:
    """Where the migration and the seed mirror disagree about the repoint, one line each.

    Read through the module rather than off the names imported above, so a test can move one
    writer and see the other stay put -- which is the half-repoint this file exists to catch.
    """
    found = []
    if f"'{mirror.EVIDENCE_TAG}'" not in migration:
        found.append(f"the migration does not quote evidence_tag {mirror.EVIDENCE_TAG}")
    if f"'{mirror.EVIDENCE_COMMIT}'" not in migration:
        found.append(f"the migration does not quote evidence_commit {mirror.EVIDENCE_COMMIT}")
    if f"date '{mirror.REGISTERED_ON.isoformat()}'" not in migration:
        found.append(f"the migration does not carry the clock {mirror.REGISTERED_ON}")
    return found


def test_the_migration_and_the_mirror_agree_about_being_repointed() -> None:
    """A half-repoint is two different claims about when these rows were published. The
    release gate refuses one; this says so without waiting for a tag.

    Both literals, whichever state the pair is in. The earlier form asserted the quoted tag was
    absent *unless* it was the placeholder, which is true only while the tag is UNRELEASED and
    false after every repoint by construction: it went red the day v0.76 did what the repoint
    checklist asks, and stayed red on main from `1ab596c`. A gate that a correct repoint breaks
    is a gate nobody can act on.
    """
    migration = MIGRATION.read_text(encoding="utf-8")

    assert repoint_disagreements(migration) == []
    # And the pair agrees with itself: a tag repointed without its commit, or the reverse, is
    # the half-repoint the release gate refuses, and neither file's own copy can see it.
    assert (mirror.EVIDENCE_TAG == "UNRELEASED") == (
        mirror.EVIDENCE_COMMIT == "0" * 40
    )
    # Shape only. This pattern accepts the placeholder, and deliberately: an unrepointed pair is
    # a legitimate state between writing a migration and cutting the release that publishes it,
    # and `release.py`'s placeholder_evidence_blockers is what refuses to ship one.
    assert REPOINTED_COMMIT.match(EVIDENCE_COMMIT)


# One arm each, because a check with a negative case on one of three is two checks nobody has
# tried to break. The clock is the one 073 spends five lines warning about: it is written twice
# in the migration and both copies have to move together.
MOVED_ALONE = (
    ("EVIDENCE_TAG", "v9.99-never-cut", "does not quote evidence_tag v9.99-never-cut"),
    ("EVIDENCE_COMMIT", "f" * 40, f"does not quote evidence_commit {'f' * 40}"),
    ("REGISTERED_ON", date(2019, 1, 1), "does not carry the clock 2019-01-01"),
)


@pytest.mark.parametrize(
    ("moved", "value", "named"), MOVED_ALONE, ids=[row[0] for row in MOVED_ALONE]
)
def test_a_mirror_moved_alone_is_caught_on_every_arm(
    monkeypatch: pytest.MonkeyPatch, moved: str, value: object, named: str
) -> None:
    """The negative case the inverted form never had: move one value on the mirror and nothing
    else, and the check has to name the writer that did not move with it."""
    migration = MIGRATION.read_text(encoding="utf-8")
    monkeypatch.setattr(mirror, moved, value)

    assert repoint_disagreements(migration) == [f"the migration {named}"], moved


def test_the_migration_carries_every_registration_and_every_rule() -> None:
    """Not a parse: the database gate compares rows. This catches a mirror edited alone."""
    migration = MIGRATION.read_text(encoding="utf-8")

    for row in JURISDICTIONS:
        assert f"'{row['jurisdiction_code']}', '{row['name']}'" in migration
        assert f"'{row['identity_prefix']}'" in migration
    # The founding set alone: the decisions this train registers are published by the
    # presentation migration, whose own test reads them there.
    for rule in JURISDICTION_RULES_AS_FOUNDED:
        assert f"'{rule['rule_id']}'" in migration


def test_every_registration_declares_the_decisions_no_jurisdiction_may_lack() -> None:
    serving = {
        (rule["jurisdiction_code"], rule["decision"])
        for rule in (rule_parameters(row) for row in JURISDICTION_RULES)
        if rule["serving"]
    }

    for row in JURISDICTIONS:
        for decision in REQUIRED_DECISIONS:
            assert (row["jurisdiction_code"], decision) in serving


def test_one_serving_rule_per_decision_and_montana_carries_the_other_one_anyway() -> None:
    """MT files inventory twice, at well grain and at PRU lease grain. The registry names both
    and serves one; a scalar column would have had to pick silently."""
    serving: list[tuple[object, object]] = []
    for row in (rule_parameters(rule) for rule in JURISDICTION_RULES):
        if row["serving"]:
            serving.append((row["jurisdiction_code"], row["decision"]))

    assert len(serving) == len(set(serving))
    montana = [
        row
        for row in JURISDICTION_RULES
        if row["jurisdiction_code"] == "MT" and row["decision"] == "inventory_jurisdiction"
    ]
    assert len(montana) == 2
    assert [rule_parameters(row)["serving"] for row in montana] == [True, False]
    assert rule_parameters(montana[1])["note"] == "PRU lease grain"


def test_every_tile_layer_named_by_a_registration_is_a_published_layer() -> None:
    """`tiles.py` keeps its per-state column lists by hand (§1.2); the registry may only name
    one of them, never invent one."""
    published = {layer.name for layer in TILE_LAYERS}

    for row in JURISDICTIONS:
        assert row["wells_tile_layer_id"] in published


def test_every_map_colour_is_a_brand_colour_or_a_status_class_colour() -> None:
    """A registration's colour is a promise about what the canvas draws, so it has to be a
    colour the canvas already has a name for."""
    palette = BRAND.read_text(encoding="utf-8") + STATUS_CLASSES.read_text(encoding="utf-8")

    for row in JURISDICTIONS:
        assert str(row["map_colour"]) in palette


def test_the_identity_pattern_is_derived_from_the_prefix_and_not_restated() -> None:
    for row in JURISDICTIONS:
        prefix = str(row["identity_prefix"])
        assert identity_pattern(prefix) == f"^{prefix}[0-9]{{8}}$"
        assert re.match(identity_pattern(prefix), f"{prefix}12345678")
        assert not re.match(identity_pattern(prefix), f"{prefix}1234567")


def test_the_allowlists_the_add_a_state_scan_reads_are_derived_from_the_rows() -> None:
    """P5's scan takes its allowlist from here. Restated by hand it would drift on the first
    registration that is added to one and not the other."""
    assert sorted(PREFIXES) == ["25", "30", "33", "42"]
    assert sorted(CODES) == sorted(row["jurisdiction_code"] for row in JURISDICTION_CODES)
    assert sorted(NAMES) == sorted(row["name"] for row in JURISDICTIONS)
    assert len(PREFIXES) == len(JURISDICTIONS)


def test_every_runtime_consumer_still_reads_four_rows() -> None:
    """M-16. Two consumers build *tuples* from JURISDICTIONS and put them straight into
    derivation params, so a seed that grew to eight rows would have moved two mart addresses --
    `marts.nd_neighbors` and `marts.land_metrics` -- from a phase that touches neither."""
    from glasswell.marts.land_metrics import GRID_SCOPE_API_PREFIXES, GRID_STATE_API_PREFIXES
    from glasswell.marts.neighbors import STATE_CODES

    assert len(JURISDICTIONS) == 4
    assert len(STATE_CODES) == 2
    assert len(set(STATE_CODES)) == len(STATE_CODES)
    assert GRID_STATE_API_PREFIXES == ("33",)
    assert GRID_SCOPE_API_PREFIXES == ("33",)


def test_the_founding_rows_are_the_resolved_ones_without_the_presentation_columns() -> None:
    """One declaration, two clocks. A second copy of four rationales would drift on the first
    correction that touched one and not the other."""
    assert len(JURISDICTION_RESTATEMENTS) == len(JURISDICTIONS)
    for founding, resolved in zip(JURISDICTION_RESTATEMENTS, JURISDICTIONS, strict=True):
        assert set(resolved) - set(founding) == set(PRESENTATION_COLUMNS)
        assert all(founding[key] == resolved[key] for key in founding)


def test_every_wells_row_carries_a_subtitle_the_census_can_fill() -> None:
    for row in JURISDICTIONS:
        assert "{count}" in str(row["wells_subtitle_template"])
        assert row["wells_layer_id"] in str(row["wells_style_layer_ids"])
    orders = [row["wells_draw_order"] for row in JURISDICTIONS]
    assert len(set(orders)) == len(orders)


def test_both_of_the_restatement_placeholders_are_literals_the_release_gate_can_see() -> None:
    """`release.py` scans the mirror for the *quoted literal*, not for the value, so an
    expression that evaluates to forty zeros is invisible to it: the tag alone would block, and
    a repoint that moved the tag and left the commit would clear the gate with a placeholder
    still on its way to an append-only table. Written as a literal, like `EVIDENCE_COMMIT`."""
    mirror = (ROOT / "src/glasswell/seed/jurisdictions.py").read_text(encoding="utf-8")

    assert f'"{RESTATED_EVIDENCE_TAG}"' in mirror
    assert f'"{RESTATED_EVIDENCE_COMMIT}"' in mirror
    assert '"0" * 40' not in mirror
    assert REPOINTED_COMMIT.match(RESTATED_EVIDENCE_COMMIT)


def test_the_ledgers_absence_class_is_the_word_the_canvas_draws() -> None:
    """One word, two languages, and nothing between them until this.

    The server never emitted the string before v0.77: the client coalesced a null status to it
    on the tile wire and the ledger dropped the bucket. Now the writer puts it in
    `lineage.jurisdiction_well_counts` and the client keys its census on it, so a rename on
    either side would leave every suite green and the absence class back to a muted row with no
    measurement -- the exact state this train exists to leave.
    """
    source = STATUS_CLASSES.read_text(encoding="utf-8")
    declared = ABSENCE_CLASS.search(source)

    assert declared is not None, "web/src/map/status.ts declares no UNMAPPED_STATUS id"
    assert declared.group(1) == UNMAPPED_CLASS
    # Once, in the declaration: a bare copy elsewhere in the file is a third spelling that this
    # comparison would not see move.
    assert source.count(f'"{UNMAPPED_CLASS}"') == 1
