"""M-4: every ingest path records the build identity the unit already exports.

`infra/systemd/glasswell-ingest.service` loads `GLASSWELL_LOCKFILE_SHA256`, and
`resolve_environment` folds it into the `env_id` fingerprint. Two of the three paths had a
near-identical private copy that inserted `python_version` only, so ten of twenty-two live
derivations were unpinned — partial by ingest path rather than by lockfile tooling (R7/C8).
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from glasswell.ingest.base import LOCKFILE_SHA256_ENV, resolve_environment
from glasswell.ingest.nd_gis import load_wells
from glasswell.lineage.capture import lineage_session
from glasswell.lineage.store import PostgresRecorder
from glasswell.seed import seed_all

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "nd_gis"
WELLS_ARCHIVE = FIXTURES / "OGD_Wells_300.zip"
SOURCE_ROOT = Path(__file__).resolve().parents[2] / "src" / "glasswell"
BASE_MODULE = SOURCE_ROOT / "ingest" / "base.py"
LOCKFILE = "9f" * 32

_ENVIRONMENT_OF = """
select e.env_id, e.lockfile_sha256, count(*)
  from lineage.derivations d join lineage.environments e on e.env_id = d.env_id
 group by e.env_id, e.lockfile_sha256
"""


def client_for(archive: Path) -> httpx.Client:
    payload = archive.read_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=payload, headers={"content-type": "application/zip"})

    return httpx.Client(transport=httpx.MockTransport(handler))


def rows(connection, sql: str, *parameters: object) -> list[tuple]:
    with connection.cursor() as cursor:
        cursor.execute(sql, parameters or None)
        return cursor.fetchall()


@pytest.fixture
def pinned(monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv(LOCKFILE_SHA256_ENV, LOCKFILE)
    return LOCKFILE


def test_the_resolved_environment_records_the_lockfile(db, pinned):
    environment = resolve_environment(db)

    assert environment.env_id.startswith("env_")
    assert rows(
        db, "select lockfile_sha256 from lineage.environments where env_id = %s",
        environment.env_id,
    ) == [(pinned,)]


def test_an_explicit_env_id_is_an_override_of_the_name_not_of_the_pin(db, pinned):
    """`--env-id` stays available; it must not be a way to drop the lockfile again."""
    environment = resolve_environment(db, env_id="env_cli")

    assert environment.env_id == "env_cli"
    assert rows(
        db, "select lockfile_sha256 from lineage.environments where env_id = 'env_cli'"
    ) == [(pinned,)]


def test_an_unset_lockfile_is_recorded_as_absent_not_invented(db, monkeypatch):
    monkeypatch.delenv(LOCKFILE_SHA256_ENV, raising=False)

    environment = resolve_environment(db)

    assert rows(
        db, "select lockfile_sha256 from lineage.environments where env_id = %s",
        environment.env_id,
    ) == [(None,)]


def test_a_gis_derivation_carries_the_pin_the_unit_exports(db, raw_root, pinned):
    """The path `main()` takes: resolve the environment, then load under it."""
    seed_all(db)
    db.commit()
    environment = resolve_environment(db)
    with lineage_session(
        recorder=PostgresRecorder(db), environment=environment
    ), client_for(WELLS_ARCHIVE) as client:
        load_wells(db, raw_root=raw_root, client=client)
    db.commit()

    recorded = rows(db, _ENVIRONMENT_OF)
    assert recorded, "the GIS load produced no derivation to check"
    assert {lockfile for _, lockfile, _ in recorded} == {pinned}


