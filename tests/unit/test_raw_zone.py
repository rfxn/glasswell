from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from glasswell.lineage.errors import RawRootUnset
from glasswell.lineage.fetch import (
    RAW_ROOT_ENV,
    _artifact_directory,
    _extension,
    _slug,
    _upstream_mtime,
    resolve_raw_root,
)

FETCHED_AT = datetime(2026, 8, 1, 5, 2, 11, tzinfo=UTC)
RUN_VINTAGE = date(2026, 8, 1)


def test_the_raw_root_prefers_the_explicit_argument(monkeypatch):
    monkeypatch.setenv(RAW_ROOT_ENV, "/srv/glasswell/raw")
    assert resolve_raw_root("/tmp/somewhere") == Path("/tmp/somewhere")


def test_the_raw_root_falls_back_to_the_environment(monkeypatch):
    monkeypatch.setenv(RAW_ROOT_ENV, "/srv/glasswell/raw")
    assert resolve_raw_root() == Path("/srv/glasswell/raw")


def test_an_undeclared_raw_root_refuses_rather_than_writing_beside_the_operator(
    monkeypatch, tmp_path
):
    """The default was `data/raw`, resolved against the process's working directory, so the
    same ingest wrote to a different filesystem depending on where it was started -- `/` under
    systemd-run, a home directory by hand -- and `.incoming`'s same-device precheck then passed
    for the wrong device. A production write has no default."""
    monkeypatch.delenv(RAW_ROOT_ENV, raising=False)
    monkeypatch.chdir(tmp_path)

    with pytest.raises(RawRootUnset, match=RAW_ROOT_ENV) as refusal:
        resolve_raw_root()

    assert "/etc/glasswell/app.env" in str(refusal.value)
    assert not (tmp_path / "data").exists()


def test_an_empty_declaration_is_not_a_declaration(monkeypatch):
    """An EnvironmentFile that carries `GLASSWELL_RAW_ROOT=` sets it to the empty string, and
    Path("") is the working directory again."""
    monkeypatch.setenv(RAW_ROOT_ENV, "")

    with pytest.raises(RawRootUnset):
        resolve_raw_root()


@pytest.mark.parametrize(
    ("source_key", "expected"),
    [
        ("2026_03.xlsx", "2026-03-xlsx"),
        ("OGD_Horizontals_Line.zip", "ogd-horizontals-line-zip"),
        ("wcproduction.zip", "wcproduction-zip"),
        ("//", "artifact"),
    ],
)
def test_the_source_key_slug_is_filesystem_safe(source_key, expected):
    assert _slug(source_key) == expected


@pytest.mark.parametrize(
    ("source_key", "expected"), [("2026_03.xlsx", ".xlsx"), ("PDQ_DSV", ".bin")]
)
def test_the_payload_keeps_the_upstream_extension(source_key, expected):
    assert _extension(source_key) == expected


def test_the_artifact_directory_is_unique_by_vintage_time_and_hash():
    directory = _artifact_directory(
        Path("/raw"), "nd_mpr_xlsx", "2026_03.xlsx", RUN_VINTAGE, FETCHED_AT, "a" * 64
    )
    assert directory == Path("/raw/nd_mpr_xlsx/2026-03-xlsx/2026-08-01T050211Z-aaaaaaaaaaaa")


def test_the_artifact_directory_is_dated_by_the_run_vintage_not_the_landing_time():
    """DR-31: bytes landing after midnight still file under the day their run opened."""
    directory = _artifact_directory(
        Path("/raw"),
        "nd_mpr_xlsx",
        "2026_03.xlsx",
        date(2026, 5, 14),
        datetime(2026, 5, 15, 0, 0, 30, tzinfo=UTC),
        "a" * 64,
    )
    assert directory.name == "2026-05-14T000030Z-aaaaaaaaaaaa"


def test_a_malformed_upstream_date_is_not_a_fetch_failure():
    assert _upstream_mtime({"last-modified": "Tue, 18 Aug 2026 06:15:00 GMT"}) is not None
    assert _upstream_mtime({"last-modified": "whenever"}) is None
    assert _upstream_mtime({}) is None


def test_a_promotion_opens_a_run_without_declaring_a_raw_zone_it_never_reaches(monkeypatch):
    """`open_ingest_run` used to resolve the root as the run opened, so a promotion that reads
    staging and writes canonical -- co_wells, co_production, nm_wells, nm_dims, repromote --
    would refuse over a raw zone it never touches. It is resolved where it is reached."""
    from glasswell.ingest.base import IngestRun

    monkeypatch.delenv(RAW_ROOT_ENV, raising=False)
    run = IngestRun(connection=None, session=None, as_of=None)

    with pytest.raises(RawRootUnset):
        _ = run.raw_root

    monkeypatch.setenv(RAW_ROOT_ENV, "/data/raw")
    assert run.raw_root == Path("/data/raw")


def test_an_empty_argument_is_not_a_declaration_either(monkeypatch, tmp_path):
    """H-2. The empty check guarded the environment branch and not the argument, so
    `--raw-root ""` resolved to `Path('')` -- the working directory itself, which is worse than
    the relative default it replaced."""
    monkeypatch.delenv(RAW_ROOT_ENV, raising=False)
    monkeypatch.chdir(tmp_path)

    with pytest.raises(RawRootUnset):
        resolve_raw_root("")

    monkeypatch.setenv(RAW_ROOT_ENV, "/data/raw")
    # The environment is not consulted for an argument that was passed and was empty.
    with pytest.raises(RawRootUnset):
        resolve_raw_root("")


def test_a_read_path_answers_not_found_rather_than_five_hundred(monkeypatch):
    """H-3. `api/routers/lineage.py`'s containment check calls the same resolver on a read path.
    `RawRootUnset` has no problem-document mapping, so letting it out turned a clean 404 into a
    500 on a host that declares no raw zone."""
    from glasswell.api.routers.lineage import _payload_within_raw_zone

    monkeypatch.delenv(RAW_ROOT_ENV, raising=False)

    assert _payload_within_raw_zone("/data/raw/tx_pdq_dsv/x/payload.zip") is None
