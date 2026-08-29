"""An empty layer is not a harvest. The walk's reconciliation reads `0 == 0 == 0` and passes,
so a layer returning no features produced a zero-byte artifact whose sha256 is the digest of the
empty string — carrying no source-identifying bytes at all. `blm_plss_townships` and
`blm_plss_sections` walk one BLM CadNSDI MapServer under the scope `PLSSID LIKE 'ND%'`
(`cr_blm_plss_scope_1`), so a prefix change upstream empties both slots and the two zero-byte
artifacts collide by construction (F8)."""

from __future__ import annotations

import hashlib

import pytest

from glasswell.ingest.arcgis import EmptyWalk, _walk
from tests.support.arcgis_fake import SERVICE_PATH, FakeArcGis

pytestmark = pytest.mark.unit

SERVICE_URL = f"https://gis.blm.gov{SERVICE_PATH}"
EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()


def walk(fake: FakeArcGis, destination):
    with fake.client() as client:
        return _walk(
            client,
            destination,
            service_url=SERVICE_URL,
            layer_id=2,
            where="PLSSID LIKE 'ZZ%'",
            page_size=2,
            page_delay_seconds=0.0,
        )


def test_a_layer_with_no_matching_features_is_refused(tmp_path):
    destination = tmp_path / "payload.geojsonl"

    with pytest.raises(EmptyWalk) as refusal:
        walk(FakeArcGis(count_override={2: 0}), destination)

    assert "PLSSID LIKE 'ZZ%'" in str(refusal.value)
    assert str(refusal.value).count(SERVICE_URL) == 1


def test_the_refusal_names_a_reason_code_the_failure_ledger_can_record(tmp_path):
    with pytest.raises(EmptyWalk) as refusal:
        walk(FakeArcGis(count_override={2: 0}), tmp_path / "payload.geojsonl")

    assert refusal.value.glasswell_reason == "empty_walk"


def test_no_zero_byte_artifact_survives_the_refusal(tmp_path):
    """Whatever the caller does next, it must not be handed bytes that hash to the empty
    string: every empty harvest from every source shares that one address."""
    destination = tmp_path / "payload.geojsonl"

    with pytest.raises(EmptyWalk):
        walk(FakeArcGis(count_override={2: 0}), destination)

    assert not destination.exists() or destination.read_bytes() != b""


def test_a_layer_with_features_still_walks(tmp_path):
    """The floor under the refusal: the non-empty path is untouched."""
    result = walk(FakeArcGis(), tmp_path / "payload.geojsonl")

    assert result.size_bytes > 0
    assert result.sha256 != EMPTY_SHA256
