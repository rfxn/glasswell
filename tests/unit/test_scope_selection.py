"""`make test` may run less than the whole suite; every way it narrows has to be provable.

The tool is local-only by measurement (it selects the whole suite on five of the last six
merges), and CI never trusts it — but a false negative here is a fix round the developer pays
for, so each narrowing rule gets a case in both directions.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("test_scope", ROOT / "scripts" / "test-scope.py")
scope = importlib.util.module_from_spec(_spec)
sys.modules["test_scope"] = scope
_spec.loader.exec_module(scope)


def selection(paths: list[str], base: str | None = None) -> tuple[list[str], list[str]]:
    return scope.select(paths, base)


def test_a_tier_conftest_selects_its_whole_tier() -> None:
    """A conftest collects no tests, so naming the file selects nothing. Every test in the tier
    builds on it."""
    selected, reasons = selection(["tests/contract/conftest.py"])

    assert "tests/contract" in selected, (selected, reasons)


@pytest.mark.parametrize("tier", ["contract", "integration", "unit"])
def test_every_tier_conftest_selects_that_tier(tier: str) -> None:
    selected, _ = selection([f"tests/{tier}/conftest.py"])

    assert f"tests/{tier}" in selected


def test_the_root_conftest_still_selects_the_whole_suite() -> None:
    selected, reasons = selection(["tests/conftest.py"])

    assert selected == ["tests"]
    assert any("reaches every tier" in reason for reason in reasons)


def test_a_pyproject_change_it_cannot_read_falls_back_to_the_whole_suite() -> None:
    """The tool saw `pyproject.toml` in the diff; if it cannot then prove every changed line is
    the version string, it has not earned the right to narrow. It used to look only at the
    working tree, so a *committed* dependency edit — which is what this branch did — produced an
    empty diff and was dropped from the selection entirely."""
    selected, reasons = selection(["pyproject.toml"])

    assert selected == ["tests"]
    assert any("pyproject.toml" in reason for reason in reasons)


def test_a_version_only_pyproject_edit_does_not_widen_the_selection(tmp_path: Path) -> None:
    assert scope.only_the_version_changed(
        '-version = "0.81"\n+version = "0.82"\n'
    )
    assert not scope.only_the_version_changed(
        '-version = "0.81"\n+version = "0.82"\n+  "pytest-xdist",\n'
    )
    assert not scope.only_the_version_changed("")


def test_a_source_module_selects_the_tests_that_import_it() -> None:
    selected, reasons = selection(["src/glasswell/ingest/tx_pdq.py"])

    assert not reasons
    assert "tests/unit" in selected
    assert "tests/integration/test_tx_lease_promote.py" in selected
    assert "tests/unit/test_tx_pdq_parse.py" in selected
    assert "tests/contract/test_wells.py" not in selected


def test_a_migration_falls_back_because_the_graph_cannot_read_it() -> None:
    selected, reasons = selection(["src/glasswell/db/migrations/081_tx_pdq_format.sql"])

    assert selected == ["tests"]
    assert any("data the graph cannot read" in reason for reason in reasons)
