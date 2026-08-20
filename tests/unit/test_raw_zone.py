from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from glasswell.lineage.fetch import (
    DEFAULT_RAW_ROOT,
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


def test_the_raw_root_falls_back_to_the_environment_then_a_local_default(monkeypatch):
    monkeypatch.setenv(RAW_ROOT_ENV, "/srv/glasswell/raw")
    assert resolve_raw_root() == Path("/srv/glasswell/raw")
    monkeypatch.delenv(RAW_ROOT_ENV)
    # Never /srv by default: a test run must not be able to write the production raw zone (C1).
    assert resolve_raw_root() == DEFAULT_RAW_ROOT
    assert not str(DEFAULT_RAW_ROOT).startswith("/")


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
