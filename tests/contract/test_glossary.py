"""`/v1/glossary` (DIR-8): the glossary is data served through the same rules as the rest."""

from __future__ import annotations

from fastapi.testclient import TestClient

from glasswell.seed.glossary import load_glossary_seed

# Derived rather than written down: O-6 adds glossary rows every phase, and a literal here
# turns each of those into a second, unrelated red. `gt_service_well` is inserted by migration
# 027 instead of being seeded, so it is the one term the file cannot count.
SEEDED_TERMS = len(load_glossary_seed()) + 1
STOPWORD_TERMS = 9


def test_every_seeded_term_is_served(client: TestClient) -> None:
    data = client.get("/v1/glossary", params={"limit": 200}).json()["data"]

    assert len(data) == SEEDED_TERMS
    assert all(item["short_definition"] for item in data)


def test_terms_are_ordered_alphabetically(client: TestClient) -> None:
    data = client.get("/v1/glossary", params={"limit": 200}).json()["data"]

    assert [item["term"] for item in data] == sorted(item["term"] for item in data)


def test_the_collection_searches_terms_and_aliases(client: TestClient) -> None:
    by_term = client.get("/v1/glossary", params={"q": "report vintage"}).json()["data"]

    assert [item["term_id"] for item in by_term] == ["gt_report_vintage"]


def test_the_collection_filters_on_domain_tag(client: TestClient) -> None:
    data = client.get("/v1/glossary", params={"domain_tag": "lineage"}).json()["data"]

    assert data
    assert all("lineage" in item["domain_tags"] for item in data)


def test_a_term_resolves_by_id_and_by_surface_form(client: TestClient) -> None:
    """DIR-8 writes /glossary/{term}; an agent holding a meta.labels value has an id."""
    by_id = client.get("/v1/glossary/gt_report_vintage").json()["data"]
    by_word = client.get("/v1/glossary/Report Vintage").json()["data"]

    assert by_id == by_word
    assert by_id["expanded_definition"]
    assert by_id["related_terms"]
    assert by_id["source_refs"]


def test_the_detail_names_where_the_term_appears(client: TestClient) -> None:
    data = client.get("/v1/glossary/gt_report_vintage").json()["data"]

    assert {entry["kind"] for entry in data["appears_in"]} == {"api_field"}
    assert any(entry["ref"].startswith("/v1/") for entry in data["appears_in"])


def test_an_unknown_term_is_not_found(client: TestClient) -> None:
    assert client.get("/v1/glossary/gt_nothing").status_code == 404


def test_the_index_is_pre_lowercased_and_expanded(client: TestClient) -> None:
    data = client.get("/v1/glossary/index").json()["data"]

    surfaces = {entry["surface"] for entry in data["entries"]}
    assert surfaces
    assert all(surface == surface.lower() for surface in surfaces)
    assert all(entry["n_words"] >= 1 for entry in data["entries"])
    assert data["index_version"].startswith("gix_")


def test_the_index_excludes_stopwords_from_scanning(client: TestClient) -> None:
    """M7: longest-match scanning with no stopword list underlines every third word."""
    data = client.get("/v1/glossary/index").json()["data"]

    assert len(data["stopwords"]) >= STOPWORD_TERMS
    assert "stream" in data["stopwords"]
    assert "stream" not in {entry["surface"] for entry in data["entries"]}


def test_stopword_terms_stay_reachable_by_id(client: TestClient) -> None:
    response = client.get("/v1/glossary/gt_stream")

    assert response.status_code == 200
    assert response.json()["data"]["highlightable"] is False
