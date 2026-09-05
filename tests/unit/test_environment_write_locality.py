"""M-4: only `ingest/base.py` writes a `lineage.environments` row, read off the source tree.

The database half of M-4 — that a load's derivations carry the fingerprint the unit exported —
stays in `tests/integration/test_ingest_environment.py`. These three read source files and
nothing else, and a second private copy of the helper is how the pin got dropped, so they are
worth failing in the two-minute tier rather than behind a container.
"""

from __future__ import annotations

from pathlib import Path

import pytest

SOURCE_ROOT = Path(__file__).resolve().parents[2] / "src" / "glasswell"
BASE_MODULE = SOURCE_ROOT / "ingest" / "base.py"


@pytest.mark.parametrize("module", ["ingest/nd_gis.py", "marts/nd_wells.py"])
def test_no_module_writes_its_own_environment_row(module):
    """The helper is two modules away; a second copy is how the pin got dropped."""
    source = (SOURCE_ROOT / module).read_text(encoding="utf-8")

    assert "lineage.environments" not in source
    assert "resolve_environment" in source


def test_only_the_shared_helper_inserts_an_environment():
    writers = sorted(
        path.relative_to(SOURCE_ROOT).as_posix()
        for path in SOURCE_ROOT.rglob("*.py")
        if "insert into lineage.environments" in path.read_text(encoding="utf-8")
    )

    assert writers == [BASE_MODULE.relative_to(SOURCE_ROOT).as_posix()]
