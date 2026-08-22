"""The §1.2.1 walk contract, off the fixture double: order, caps, counts, refusals."""

from __future__ import annotations

import hashlib
import json

import httpx
import pytest

from glasswell.ingest.arcgis import (
    HostNotAllowlisted,
    HostTokenGated,
    LayerNotPaginable,
    PageWalkIncomplete,
    _walk,
    arcgis_rest_paginate,
)
from tests.support.arcgis_fake import SERVICE_PATH, FakeArcGis

SERVICE_URL = f"https://gis.blm.gov{SERVICE_PATH}"


def walk(fake: FakeArcGis, destination, layer_id=2, page_size=2):
    with fake.client() as client:
        return _walk(
            client,
            destination,
            service_url=SERVICE_URL,
            layer_id=layer_id,
            where="PLSSID LIKE 'ND%'",
            page_size=page_size,
            page_delay_seconds=0.0,
        )


def test_the_walk_is_paged_ordered_and_fully_accounted(tmp_path):
    fake = FakeArcGis()
    result = walk(fake, tmp_path / "payload.geojsonl")
    assert result.acquisition_params["pages"] == 2
    assert result.acquisition_params["features_written"] == 4
    assert result.acquisition_params["count_before"] == 4
    assert result.acquisition_params["count_after"] == 4
    assert result.acquisition_params["order_by"] == "OBJECTID ASC"
    assert result.acquisition_params["out_sr"] == 4269
    assert result.acquisition_params["result_record_count"] == 2
    assert result.acquisition_params["format"] == "geojson"
    assert len(result.acquisition_params["layer_json_sha256"]) == 64
    pages = [
        request
        for request in fake.requests
        if "resultOffset" in request.url.params
    ]
    assert [request.url.params["orderByFields"] for request in pages] == ["OBJECTID ASC"] * 2
    assert [request.url.params["resultOffset"] for request in pages] == ["0", "2"]


def test_identical_upstream_state_assembles_to_identical_bytes(tmp_path):
    first = walk(FakeArcGis(), tmp_path / "one.geojsonl")
    second = walk(FakeArcGis(), tmp_path / "two.geojsonl")
    assert first.sha256 == second.sha256
    content = (tmp_path / "one.geojsonl").read_bytes()
    assert hashlib.sha256(content).hexdigest() == first.sha256
    lines = content.decode("utf-8").splitlines()
    assert len(lines) == 2
    for line in lines:
        collection = json.loads(line)
        assert collection["type"] == "FeatureCollection"


def test_the_page_size_never_exceeds_the_advertised_maximum(tmp_path):
    fake = FakeArcGis()
    result = walk(fake, tmp_path / "payload.geojsonl", page_size=5000)
    # layer_2.json advertises maxRecordCount 2000: read, never guessed and never exceeded.
    assert result.acquisition_params["result_record_count"] == 2000


def test_a_count_disagreement_fails_the_walk(tmp_path):
    fake = FakeArcGis(count_override={2: 5})
    with pytest.raises(PageWalkIncomplete):
        walk(fake, tmp_path / "payload.geojsonl")


def test_a_mid_walk_upstream_change_fails_the_walk(tmp_path):
    fake = FakeArcGis(count_after_override={2: 3})
    with pytest.raises(PageWalkIncomplete):
        walk(fake, tmp_path / "payload.geojsonl")


def test_a_token_gate_halts_the_service_path(tmp_path):
    fake = FakeArcGis(token_gate_code=499)
    with pytest.raises(HostTokenGated):
        walk(fake, tmp_path / "payload.geojsonl")
    assert len(fake.requests) == 1  # no sibling retry, no fallback mirror


def test_a_layer_without_pagination_is_not_an_ingest_path(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"name": "x", "maxRecordCount": 1000, "fields": []})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client, pytest.raises(
        LayerNotPaginable
    ):
        _walk(
            client,
            tmp_path / "payload.geojsonl",
            service_url=SERVICE_URL,
            layer_id=2,
            where="1=1",
            page_size=None,
            page_delay_seconds=0.0,
        )


def test_an_unallowlisted_host_is_refused_before_any_request():
    with pytest.raises(HostNotAllowlisted):
        arcgis_rest_paginate(
            None,  # type: ignore[arg-type] — refused before the connection is touched
            "blm_plss_sections",
            "nd_sections.geojsonl",
            service_url="https://evil.example/arcgis/rest/services/X/MapServer",
            layer_id=2,
            where="1=1",
        )
