"""The registry's own data, held to the things no database constraint can see.

The registrations ship on two paths -- migration 072 and `seed/jurisdictions.py` -- and the
database gate that holds the two together needs docker. These are the ones that do not: that
the two paths agree about the repoint, that every declared tile layer and colour exists, and
that each registration carries the decision no jurisdiction may be without.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from glasswell.marts.tiles import TILE_LAYERS
from glasswell.seed.jurisdictions import (
    CODES,
    EVIDENCE_COMMIT,
    EVIDENCE_TAG,
    JURISDICTION_CODES,
    JURISDICTION_RULES,
    JURISDICTIONS,
    NAMES,
    PREFIXES,
    REGISTERED_ON,
    REQUIRED_DECISIONS,
    identity_pattern,
    rule_parameters,
)

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "src/glasswell/db/migrations/072_jurisdictions.sql"
BRAND = ROOT / "BRAND.md"
STATUS_CLASSES = ROOT / "web/src/map/status.ts"
REPOINTED_COMMIT = re.compile(r"^[0-9a-f]{40}$")


def test_the_migration_and_the_mirror_agree_about_being_repointed() -> None:
    """A half-repoint is two different claims about when these rows were published. The
    release gate refuses one; this says so without waiting for a tag."""
    migration = MIGRATION.read_text(encoding="utf-8")

    assert (f"'{EVIDENCE_TAG}'" in migration) == (EVIDENCE_TAG == "UNRELEASED")
    assert (f"'{EVIDENCE_COMMIT}'" in migration) == (EVIDENCE_COMMIT == "0" * 40)
    assert REPOINTED_COMMIT.match(EVIDENCE_COMMIT)
    assert f"date '{REGISTERED_ON.isoformat()}'" in migration


def test_the_migration_carries_every_registration_and_every_rule() -> None:
    """Not a parse: the database gate compares rows. This catches a mirror edited alone."""
    migration = MIGRATION.read_text(encoding="utf-8")

    for row in JURISDICTIONS:
        assert f"'{row['jurisdiction_code']}', '{row['name']}'" in migration
        assert f"'{row['identity_prefix']}'" in migration
    for rule in JURISDICTION_RULES:
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
