"""No mart reads staging, including the ones this track adds.

Blueprint §3.0.1, and `marts/producing.py:9-10` states it in the tree. Mart-to-mart is
admissible and `marts/vintage_cohorts.py:7-8` says why while doing it; mart-to-staging is the
breach, and it is the reason Montana's lease unit had to be promoted into canonical before any
back-test could score against it.

Walked rather than listed: a mart added later is one this gate has to see without being told.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.support.layers import schema_reads_in

SOURCE = Path(__file__).resolve().parents[2] / "src" / "glasswell"
MARTS = SOURCE / "marts"
# It lives a directory up from the marts but is read by them, so the glob cannot see it and it
# has to be named. It is the only such module, and it is the one the mart tiers resolve status
# through.
STATUS_RESOLUTION = SOURCE / "status_resolution.py"
MODULES = sorted(path for path in MARTS.glob("*.py") if path.name != "__init__.py")
MODULES.append(STATUS_RESOLUTION)


def test_the_walk_finds_the_marts_it_is_meant_to_guard() -> None:
    """A gate that collected nothing would pass over anything."""
    assert len(MODULES) >= 10
    names = {path.name for path in MODULES}
    assert {"cumulatives.py", "producing.py", "wells.py", "status_resolution.py"} <= names
    assert STATUS_RESOLUTION.is_file(), "the named module moved; the walk now guards nothing"


@pytest.mark.parametrize("module", MODULES, ids=[path.stem for path in MODULES])
def test_a_mart_reads_no_staging_relation(module: Path) -> None:
    assert schema_reads_in(module, "staging") == []
