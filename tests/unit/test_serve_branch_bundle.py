"""DR-P7: `make serve-branch` served a `web/dist` it never built.

The first facet-panel visual gate very nearly judged a bundle built before the code under
review existed — the target mounts `GW_WEB_ROOT` and said nothing about how old it was, so a
browser pointed at the instance photographed whatever was last compiled. A refusal naming the
staleness is cheaper than a bundle build on every start, and unlike a build it cannot be
mistaken for the branch. `scripts/deploy.sh` refuses on the same comparison before shipping.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from tests.support.serve_branch import STALE_BUNDLE_ENV, bundle_complaint

pytestmark = pytest.mark.unit


def _tree(root: Path, *, built_after: bool) -> tuple[Path, Path]:
    sources = root / "src"
    sources.mkdir(parents=True)
    (sources / "main.ts").write_text("export const x = 1;\n", encoding="utf-8")
    dist = root / "dist"
    dist.mkdir()
    index = dist / "index.html"
    index.write_text("<!doctype html>", encoding="utf-8")
    newest = (sources / "main.ts").stat().st_mtime
    os.utime(index, (newest + 10, newest + 10) if built_after else (newest - 10, newest - 10))
    return dist, sources


def test_a_bundle_newer_than_the_source_is_served_without_comment(tmp_path: Path) -> None:
    dist, sources = _tree(tmp_path, built_after=True)

    assert bundle_complaint(dist, sources) is None


def test_a_bundle_older_than_the_source_is_refused_by_name(tmp_path: Path) -> None:
    dist, sources = _tree(tmp_path, built_after=False)

    complaint = bundle_complaint(dist, sources)

    assert complaint is not None
    assert str(dist) in complaint
    assert "npm --prefix web run build" in complaint
    # The escape hatch is in the refusal, because the vite-proxy gates do not use the bundle
    # at all and must still be able to stand the API up.
    assert STALE_BUNDLE_ENV in complaint


def test_a_directory_with_no_bundle_in_it_is_refused_too(tmp_path: Path) -> None:
    dist, sources = _tree(tmp_path, built_after=True)
    (dist / "index.html").unlink()

    complaint = bundle_complaint(dist, sources)

    assert complaint is not None
    assert "index.html" in complaint


def test_a_source_tree_that_is_not_there_is_not_a_staleness_claim(tmp_path: Path) -> None:
    """A checkout served from somewhere other than a worktree has nothing to compare against."""
    dist, _ = _tree(tmp_path, built_after=False)

    assert bundle_complaint(dist, tmp_path / "nowhere") is None
