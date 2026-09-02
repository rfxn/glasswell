"""The host verifier's check on read-time status resolution, and the API check beside it.

`refresh_status_resolution()` skips a registration whose mapping table has not landed rather
than aborting, which is right: a refresh that raised would take the migration, or the deploy's
`seed_all`, down with it. The transient case self-heals inside one deploy. The lasting one — a
`mapping_table` misspelt in a rule spec, or a map renamed by a later migration — draws that
jurisdiction's whole spine in the `unmapped` class and heals never. These two say so.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
VERIFY = ROOT / "infra" / "verify.sh"
STATUS_ROUTER = ROOT / "src" / "glasswell" / "api" / "routers" / "status.py"
MIGRATION = ROOT / "src" / "glasswell" / "db" / "migrations"


def test_the_verifier_asserts_every_read_time_vocabulary_resolves() -> None:
    """The check that catches it six months later, when nobody is deploying."""
    body = VERIFY.read_text(encoding="utf-8")

    assert "every read-time status vocabulary has resolver rows" in body
    # Against the registry rather than a list of jurisdictions: the whole point of the resolver
    # being registry-driven is that a fifth one is rows, and a check naming four would go quiet.
    assert "resolved_at' = 'read_time'" in body
    assert "lineage.status_resolution_resolved" in body
    assert "jurisdictions_as_of(current_date, current_date)" in body


def test_the_api_serves_the_same_fact_as_a_live_check() -> None:
    """`/v1/status`'s checks are the surface an operator reads without a shell on the host."""
    body = STATUS_ROUTER.read_text(encoding="utf-8")

    assert 'id="status_resolver"' in body
    assert "unresolved_read_time_jurisdictions" in body


def test_the_skip_that_makes_both_necessary_says_so_in_the_log() -> None:
    """A skip nobody can see is the defect; the notice is the first of the three signals."""
    migration = next(MIGRATION.glob("*_facet_status_resolution.sql")).read_text(encoding="utf-8")

    assert "raise notice 'status resolver:" in migration
    assert "continue;" in migration
