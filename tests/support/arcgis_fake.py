"""A fixture-backed ArcGIS MapServer double for arcgis_rest_paginate tests.

Serves the checked-in blm_plss extract through httpx.MockTransport: layer metadata verbatim,
counts and pages sliced from the recorded FeatureCollections. Never the live service.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "blm_plss"
SERVICE_PATH = "/arcgis/rest/services/Cadastral/BLM_Natl_PLSS_CadNSDI_NAD83/MapServer"

_FEATURES = {
    1: "nd_townships.geojson",
    2: "nd_sections.geojson",
}


@dataclass
class FakeArcGis:
    """One service double; `requests` records every query for order/paging assertions."""

    count_override: dict[int, int] = field(default_factory=dict)
    count_after_override: dict[int, int] = field(default_factory=dict)
    token_gate_code: int | None = None
    requests: list[httpx.Request] = field(default_factory=list)
    _counts_served: dict[int, int] = field(default_factory=dict)

    def features(self, layer_id: int) -> list[dict[str, Any]]:
        payload = json.loads((FIXTURES / _FEATURES[layer_id]).read_text(encoding="utf-8"))
        return list(payload["features"])

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._handle)

    def client(self) -> httpx.Client:
        return httpx.Client(transport=self.transport())

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.token_gate_code is not None:
            return httpx.Response(
                200,
                json={"error": {"code": self.token_gate_code, "message": "Token Required"}},
            )
        path = request.url.path
        assert path.startswith(SERVICE_PATH), f"unexpected path {path}"
        tail = path[len(SERVICE_PATH) :].strip("/").split("/")
        layer_id = int(tail[0])
        params = dict(request.url.params)
        if len(tail) == 1:
            return httpx.Response(
                200, content=(FIXTURES / f"layer_{layer_id}.json").read_bytes()
            )
        assert tail[1] == "query", f"unexpected query path {path}"
        features = self.features(layer_id)
        if params.get("returnCountOnly") == "true":
            served = self._counts_served.get(layer_id, 0)
            self._counts_served[layer_id] = served + 1
            if served and layer_id in self.count_after_override:
                return httpx.Response(200, json={"count": self.count_after_override[layer_id]})
            count = self.count_override.get(layer_id, len(features))
            return httpx.Response(200, json={"count": count})
        offset = int(params.get("resultOffset", 0))
        size = int(params.get("resultRecordCount", len(features)))
        page = features[offset : offset + size]
        return httpx.Response(
            200, json={"type": "FeatureCollection", "features": page}
        )
