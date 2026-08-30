"""`scripts/ops/nm_reregister_manifests.py` reads sidecars before it opens a transaction.

The nine New Mexico sidecars are the FK prerequisite for every canonical row Tier 1 writes, and
the tool that reads them ran for months as an untracked file in a scratch directory. What is
pinned here is the half that needs no database: the id a sidecar resolves to, and the refusal a
malformed one earns — by path, because nine files are otherwise indistinguishable in a traceback.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "ops" / "nm_reregister_manifests.py"

# The wcproduction sidecar's own digest, so the id this test asserts is the id the operator's
# dry run must print (plan T3 §4.1). Its first 32 hex characters are the manifest id's body.
WCPRODUCTION_SHA256 = "4d3bceb6a5b79880db518e00d933ae951d38232e54f8e81a4d60743491a7fb27"
WCPRODUCTION_MANIFEST_ID = "man_4d3bceb6a5b79880db518e00d933ae95"


def _load():
    spec = importlib.util.spec_from_file_location("nm_reregister_manifests", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


tool = _load()


def sidecar_payload(**overrides) -> dict:
    """The schema a real sidecar carries, from the wcproduction artifact on VM 111."""
    row = {
        "sha256": WCPRODUCTION_SHA256,
        "bytes": 968419426,
        "source_id": "nm_ocd_wcproduction",
        "source_key": "wcproduction.zip",
        "acquisition_url": "ftp://164.64.106.6/Public/OCD/volumes/wcproduction/wcproduction.zip",
        "acquisition_method": "ftp_anon",
        "acquisition_params": {"host": "164.64.106.6", "host_resolved_from": "pinned_config"},
        "fetched_at": "2026-08-20T22:44:57.515124+00:00",
        "fetch_vintage": "2026-08-20",
        "storage_uri": "/data/raw/nm_ocd_wcproduction/wcproduction-zip/x/payload.zip",
        "media_type": "application/zip",
        "upstream_mtime": "2026-08-20T00:22:40+00:00",
        "upstream_etag": None,
        "decompressed_inventory": [],
        "license_note": None,
        "redistributable": False,
    }
    row.update(overrides)
    return row


def write_sidecar(directory: Path, name: str = "manifest.json", **overrides) -> Path:
    path = directory / name
    path.write_text(json.dumps(sidecar_payload(**overrides)), encoding="utf-8")
    return path


def test_a_well_formed_sidecar_resolves_to_the_content_addressed_manifest_id(tmp_path: Path):
    row = tool.read_sidecar(write_sidecar(tmp_path))

    assert tool.manifest_id(row["sha256"]) == WCPRODUCTION_MANIFEST_ID


def test_every_key_the_registration_needs_is_required_by_name(tmp_path: Path):
    assert "sha256" in tool.REQUIRED_KEYS
    for key in tool.REQUIRED_KEYS:
        path = write_sidecar(tmp_path, name=f"{key}.json")
        payload = json.loads(path.read_text(encoding="utf-8"))
        del payload[key]
        path.write_text(json.dumps(payload), encoding="utf-8")

        with pytest.raises(tool.SidecarError) as error:
            tool.read_sidecar(path)
        assert key in str(error.value)
        assert str(path) in str(error.value)


def test_a_sidecar_missing_its_digest_exits_non_zero_and_names_the_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    path = write_sidecar(tmp_path)
    payload = sidecar_payload()
    del payload["sha256"]
    path.write_text(json.dumps(payload), encoding="utf-8")

    # No --dsn is reachable in a unit test, and none is needed: the sidecars are read first.
    status = tool.main(["--dsn", "postgresql:///unreachable", "--sidecar", str(path)])

    assert status == 1
    captured = capsys.readouterr()
    assert str(path) in captured.err
    assert "sha256" in captured.err
    assert captured.out == ""


def test_a_digest_that_is_not_a_sha256_is_refused_rather_than_prefixed(tmp_path: Path):
    path = write_sidecar(tmp_path, sha256="not-a-digest")

    with pytest.raises(tool.SidecarError) as error:
        tool.read_sidecar(path)
    assert str(path) in str(error.value)


def test_an_unparseable_fetch_timestamp_is_refused_before_any_transaction(tmp_path: Path):
    path = write_sidecar(tmp_path, fetched_at="2026-08-20 not a time")

    with pytest.raises(tool.SidecarError) as error:
        tool.read_sidecar(path)
    assert "timestamp" in str(error.value)


def test_a_null_upstream_mtime_is_a_value_not_an_absence(tmp_path: Path):
    row = tool.read_sidecar(write_sidecar(tmp_path, upstream_mtime=None))

    assert row["upstream_mtime"] is None


def test_a_sidecar_that_is_not_json_names_the_path(tmp_path: Path):
    path = tmp_path / "manifest.json"
    path.write_text("<not json>", encoding="utf-8")

    with pytest.raises(tool.SidecarError) as error:
        tool.read_sidecar(path)
    assert str(path) in str(error.value)
