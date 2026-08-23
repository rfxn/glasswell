"""The walk order is a caller's choice, because a layer's OBJECTID is not always an identity.

The NM C-115B layer is view-backed: its OBJECTID is assigned per query, so ordering an offset
walk by it re-reads and skips rows while every count reconciles (M1-9). A caller that knows a
stable total order must be able to name it; the default is unchanged.
"""

from __future__ import annotations

import pytest

from glasswell.ingest.arcgis import ArcGisFetchError, _walk
from tests.support.arcgis_fake import SERVICE_PATH, FakeArcGis

SERVICE_URL = f"https://gis.blm.gov{SERVICE_PATH}"


def walk(fake: FakeArcGis, destination, *, order_by=None):
    with fake.client() as client:
        return _walk(
            client,
            destination,
            service_url=SERVICE_URL,
            layer_id=2,
            where="PLSSID LIKE 'ND%'",
            page_size=2,
            page_delay_seconds=0.0,
            order_by=order_by,
        )


def test_the_default_order_is_still_the_object_id_field(tmp_path):
    fake = FakeArcGis()
    result = walk(fake, tmp_path / "payload.geojsonl")
    assert result.acquisition_params["order_by"] == "OBJECTID ASC"


def test_a_declared_order_is_sent_and_recorded(tmp_path):
    fake = FakeArcGis()
    order = "PLSSID ASC, FRSTDIVID ASC"
    result = walk(fake, tmp_path / "payload.geojsonl", order_by=order)
    assert result.acquisition_params["order_by"] == order
    pages = [request for request in fake.requests if "resultOffset" in request.url.params]
    assert [request.url.params["orderByFields"] for request in pages] == [order] * 2


def test_a_layer_with_no_object_id_field_still_walks_under_a_declared_order(tmp_path):
    """The OID field is required only because it was the only order available."""

    class NoOidArcGis(FakeArcGis):
        def _handle(self, request):
            response = super()._handle(request)
            if request.url.path.endswith("/2"):
                payload = response.json()
                payload["objectIdField"] = None
                payload["fields"] = [
                    field for field in payload["fields"] if field["type"] != "esriFieldTypeOID"
                ]
                return type(response)(200, json=payload)
            return response

    result = walk(NoOidArcGis(), tmp_path / "payload.geojsonl", order_by="PLSSID ASC")
    assert result.acquisition_params["features_written"] == 4

    with pytest.raises(ArcGisFetchError):
        walk(NoOidArcGis(), tmp_path / "other.geojsonl")
