"""The canonical status class domain as the seed declares it, before any database sees it.

Twelve rows with one absence class among them, a legend order no two rows share, and a swatch
no two rows share either. And the half-repoint guard: the seed is the domain's second writer,
so a release cut with the migration repointed and this file still at the placeholder would put
a permanent false publication claim into an append-only table.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from glasswell.seed.conformance_status_classes import (
    ABSENCE_BASIS_RULE_ID,
    CLASS_DOMAIN_RULE_ID,
    MAPPED_CLASSES,
    STATUS_CLASS_RULE_IDS,
    STATUS_CLASS_RULES,
)
from glasswell.seed.status_classes import (
    DOMAIN_EFFECTIVE_FROM,
    DOMAIN_EVIDENCE_COMMIT,
    DOMAIN_EVIDENCE_TAG,
    STATUS_CLASSES,
    class_parameters,
)
from glasswell.status_resolution import UNMAPPED_CLASS

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
SEED_MODULE = Path("src/glasswell/seed/status_classes.py")


def _release():
    spec = importlib.util.spec_from_file_location(
        "gw_release_domain", ROOT / "scripts/release.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


release = _release()


def rows() -> list[dict[str, object]]:
    return [class_parameters(row) for row in STATUS_CLASSES]


def test_the_domain_is_the_eleven_mapped_classes_and_one_absence_class() -> None:
    absent = [row for row in rows() if row["is_absence"]]

    assert len(absent) == 1
    assert absent[0]["status_canonical"] == UNMAPPED_CLASS
    assert tuple(
        str(row["status_canonical"]) for row in rows() if not row["is_absence"]
    ) == MAPPED_CLASSES


def test_the_legend_order_is_a_decision_and_no_two_classes_share_it() -> None:
    """Today the order is array order in a source file, which no gate can read."""
    orders = [row["sort_order"] for row in rows()]

    assert len(set(orders)) == len(orders)
    assert orders == sorted(orders)


def test_no_two_classes_are_drawn_with_the_same_swatch() -> None:
    """The pair and not the colour alone: two classes may share a colour if the glyph differs,
    and two of the eleven already do."""
    swatches = [(row["colour"], row["glyph"]) for row in rows()]
    colours = [row["colour"] for row in rows()]

    assert len(set(swatches)) == len(swatches)
    assert len(set(colours)) < len(colours), "the colour-alone constraint would be wrong here"


def test_the_absence_class_cites_the_rule_that_declares_what_absence_means() -> None:
    """N-5. One rule_id column over twelve rows, so they do not all cite the same decision: a
    rule cited by nothing served is a rule declared and orphaned."""
    cited = {str(row["rule_id"]) for row in rows()}

    assert cited == {CLASS_DOMAIN_RULE_ID, ABSENCE_BASIS_RULE_ID}
    absent = next(row for row in rows() if row["is_absence"])
    assert absent["rule_id"] == ABSENCE_BASIS_RULE_ID


def test_every_class_carries_the_domains_own_clock() -> None:
    for row in rows():
        assert row["effective_from"] == DOMAIN_EFFECTIVE_FROM
        assert row["published_at"] == DOMAIN_EFFECTIVE_FROM


def test_the_three_rules_the_domain_rests_on_are_declared_once_each() -> None:
    declared = [str(rule["rule_id"]) for rule in STATUS_CLASS_RULES]

    assert sorted(declared) == sorted(STATUS_CLASS_RULE_IDS)
    assert len(declared) == len(set(declared))


def test_the_placeholder_evidence_is_a_literal_the_release_gate_can_see() -> None:
    """An expression that evaluates to the placeholder is invisible to release.py's scan, so
    the half-repoint it exists to catch would clear the gate."""
    source = SEED_MODULE.read_text(encoding="utf-8")

    assert f'"{DOMAIN_EVIDENCE_TAG}"' in source or DOMAIN_EVIDENCE_TAG != "UNRELEASED"
    assert '"0" * 40' not in source
    assert len(DOMAIN_EVIDENCE_COMMIT) == 40


def test_a_half_repoint_that_leaves_the_domain_seed_behind_blocks_the_release(
    tmp_path: Path,
) -> None:
    """N-13. The migration and this module both carry the pair, so a repoint that moves one and
    not the other is a placeholder bound for an append-only table with a green gate in front of
    it. EVIDENCE_MIRRORS is an explicit tuple, so a new mirror is a code change or it is
    unguarded."""
    migrations = tmp_path / release.MIGRATIONS_DIR
    migrations.mkdir(parents=True)
    (migrations / "079_status_vocabulary.sql").write_text(
        "select rule_id, date '2026-09-03', 'v0.81',\n"
        "       'c8cffbc344e1ea36e454e43f3c0a4d7696aa1c0a'\n",
        encoding="utf-8",
    )
    mirror = tmp_path / SEED_MODULE
    mirror.parent.mkdir(parents=True, exist_ok=True)
    mirror.write_text(
        f'DOMAIN_EVIDENCE_TAG = "{release.PLACEHOLDER_EVIDENCE_TAG}"\n'
        f'DOMAIN_EVIDENCE_COMMIT = "{release.PLACEHOLDER_EVIDENCE_COMMIT}"\n',
        encoding="utf-8",
    )

    blockers = release.placeholder_evidence_blockers(tmp_path, release.Version(0, 81))

    assert any(SEED_MODULE.name in blocker for blocker in blockers)
    assert SEED_MODULE in release.EVIDENCE_MIRRORS
