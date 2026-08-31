"""R9 / DIR-8 coverage: every term the API names resolves to a glossary row."""

from __future__ import annotations

import psycopg
import pytest
from fastapi.testclient import TestClient

from glasswell.api.examples import EXAMPLE_API10
from tests.contract.test_naked_numbers import exercised

GLOSSARY_EXTENSION = "x-glasswell-glossary"


@pytest.fixture
def term_ids(seeded: psycopg.Connection) -> set[str]:
    with seeded.cursor() as cursor:
        cursor.execute("select term_id from canonical.glossary_terms")
        return {row[0] for row in cursor.fetchall()}


def test_every_label_the_api_emits_resolves(client: TestClient, term_ids: set[str]) -> None:
    """A label pointing at a term that does not exist is a broken hover, silently."""
    emitted: dict[str, str] = {}
    for _, call in exercised(client):
        response = client.get(call["url"], params=call["params"])
        if not response.headers["content-type"].startswith("application/json"):
            continue
        body = response.json()
        if isinstance(body, dict) and "meta" in body:
            emitted |= body["meta"]["labels"]

    assert emitted, "no response bound a field to a glossary term"
    assert {value for value in emitted.values() if value not in term_ids} == set()


def test_every_schema_binding_resolves(client: TestClient, term_ids: set[str]) -> None:
    document = client.get("/openapi.json").json()
    bound = _bindings(document)

    assert bound
    assert bound - term_ids == set()


def test_labels_are_json_pointers(client: TestClient) -> None:
    labels = client.get(f"/v1/wells/{EXAMPLE_API10}").json()["meta"]["labels"]

    assert labels, "the well detail bound no field to a term, or this test cannot fail"
    assert all(pointer.startswith("/") for pointer in labels)


def _bindings(node: object) -> set[str]:
    found: set[str] = set()
    if isinstance(node, dict):
        binding = node.get(GLOSSARY_EXTENSION)
        if isinstance(binding, str):
            found.add(binding)
        for value in node.values():
            found |= _bindings(value)
    elif isinstance(node, list):
        for value in node:
            found |= _bindings(value)
    return found
