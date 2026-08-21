"""The snapshot gate (blueprint §3.6.1, SB-04 §7.2): the contract cannot drift silently."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from glasswell.api import FREEZE, FREEZE_KEY
from glasswell.api.examples import REQUEST_EXAMPLE_KEY

SNAPSHOT_PATH = Path(__file__).with_name("openapi_snapshot.json")


def served(client: TestClient) -> str:
    return json.dumps(client.get("/openapi.json").json(), indent=2, sort_keys=True) + "\n"


def test_the_served_document_matches_the_committed_snapshot(client: TestClient) -> None:
    assert served(client) == SNAPSHOT_PATH.read_text(encoding="utf-8")


def test_the_document_states_its_own_freeze_terms(client: TestClient) -> None:
    """A change policy only a status file knows is a policy the next agent will not read."""
    freeze = client.get("/openapi.json").json()["info"][FREEZE_KEY]

    assert freeze["surface"] == "v1"
    assert freeze["status"] == "frozen"
    assert freeze["frozen_on"] == FREEZE["frozen_on"]
    assert "/v2" in freeze["policy"]


def test_every_published_operation_carries_a_request_example(client: TestClient) -> None:
    """SB-07 §10 check 1, restated at the freeze: a new path cannot arrive unexampled."""
    document = client.get("/openapi.json").json()

    missing = [
        f"{method.upper()} {path}"
        for path, operations in document["paths"].items()
        for method, operation in operations.items()
        if REQUEST_EXAMPLE_KEY not in operation
    ]

    assert missing == []
