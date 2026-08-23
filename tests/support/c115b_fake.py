"""A fixture-backed ArcGIS FeatureServer double for the C-115B capture tests.

Serves the checked-in nm_c115b extract through httpx.MockTransport: layer metadata verbatim,
counts and pages sliced from the recorded FeatureCollection. Never the live service.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "nm_c115b"
SERVICE_PATH = "/arcgis/rest/services/OCDPUB/C115B_NaturalGasWaste/FeatureServer"
SERVICE_URL = f"https://gis.emnrd.nm.gov{SERVICE_PATH}"
LAYER_ID = 0


@dataclass
class FakeC115B:
    """One service double; `requests` records every query for order/paging assertions."""

    count_override: int | None = None
    requests: list[httpx.Request] = field(default_factory=list)

    def features(self) -> list[dict[str, Any]]:
        payload = json.loads(
            (FIXTURES / "upstream_by_well.geojson").read_text(encoding="utf-8")
        )
        return list(payload["features"])

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self._handle))

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        assert path.startswith(SERVICE_PATH), f"unexpected path {path}"
        tail = path[len(SERVICE_PATH) :].strip("/").split("/")
        params = dict(request.url.params)
        if len(tail) == 1:
            return httpx.Response(200, content=(FIXTURES / "layer_0.json").read_bytes())
        assert tail[1] == "query", f"unexpected query path {path}"
        features = self.features()
        if params.get("returnCountOnly") == "true":
            count = len(features) if self.count_override is None else self.count_override
            return httpx.Response(200, json={"count": count})
        offset = int(params.get("resultOffset", 0))
        size = int(params.get("resultRecordCount", len(features)))
        return httpx.Response(
            200,
            json={"type": "FeatureCollection", "features": features[offset : offset + size]},
        )
