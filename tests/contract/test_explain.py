"""`/v1/explain`, `/v1/derivations/{id}` and `/v1/manifests` — the spine, remounted."""

from __future__ import annotations

import psycopg
from fastapi.testclient import TestClient

from glasswell.api.errors import TYPE_BASE
from glasswell.api.examples import EXAMPLE_API10, EXAMPLE_DERIVATION_ID, EXAMPLE_MANIFEST_ID
from glasswell.lineage.capture import derive, lineage_session
from glasswell.lineage.models import InputRef, OutputSpec
from glasswell.lineage.store import PostgresRecorder
from tests.contract.conftest import REPORT_VINTAGE as VINTAGE
from tests.support.fakes import FixedClock
from tests.support.seed import FIXTURE_ENV, seed_manifest


def a_production_handle(client: TestClient) -> str:
    data = client.get(f"/v1/wells/{EXAMPLE_API10}/production").json()["data"]
    return data["_lineage"]["series.oil_bbl"]


def test_a_served_number_walks_back_to_a_checksummed_file(client: TestClient) -> None:
    """S9, the thesis: chart number to terminal manifest in one call."""
    handle = a_production_handle(client)

    chain = client.get("/v1/explain", params={"h": handle, "depth": "full"}).json()["data"]

    resolved = chain["chains"][0]
    assert resolved["handle"] == handle
    assert resolved["terminals"] == [EXAMPLE_MANIFEST_ID]
    terminal = next(node for node in resolved["nodes"] if node["id"] == EXAMPLE_MANIFEST_ID)
    assert terminal["type"] == "manifest"
    assert len(terminal["sha256"]) == 64
    assert terminal["acquisition_url"]


def test_every_node_explains_itself_in_a_sentence(client: TestClient) -> None:
    """API-06: a graph the drawer cannot render as prose is not an explanation."""
    chain = client.get(
        "/v1/explain", params={"h": a_production_handle(client)}
    ).json()["data"]["chains"][0]

    assert all(node["explanation"].endswith(".") for node in chain["nodes"])


def test_explain_accepts_several_handles_at_once(client: TestClient) -> None:
    handle = a_production_handle(client)

    body = client.get("/v1/explain", params=[("h", handle), ("h", EXAMPLE_DERIVATION_ID)]).json()

    assert [chain["handle"] for chain in body["data"]["chains"]] == [
        handle,
        EXAMPLE_DERIVATION_ID,
    ]


def test_more_than_twenty_handles_is_refused(client: TestClient) -> None:
    response = client.get("/v1/explain", params=[("h", EXAMPLE_DERIVATION_ID)] * 21)

    assert response.status_code == 422
    assert response.json()["type"] == f"{TYPE_BASE}/validation_failed"


def test_depth_is_capped_rather_than_silently_clamped(client: TestClient) -> None:
    response = client.get(
        "/v1/explain", params={"h": EXAMPLE_DERIVATION_ID, "depth": "9"}
    )

    assert response.status_code == 422


def test_explain_requires_at_least_one_handle(client: TestClient) -> None:
    assert client.get("/v1/explain").status_code == 422


def test_the_derivation_record_is_retrievable(client: TestClient) -> None:
    data = client.get(f"/v1/derivations/{EXAMPLE_DERIVATION_ID}").json()["data"]

    assert data["derivation_id"] == EXAMPLE_DERIVATION_ID
    assert data["operation"] == "canonical.promote"
    assert data["determinism_class"] == "D1"
    assert data["code_dirty"] is False
    assert "inputs" not in data


def test_include_expands_inputs_and_rules(client: TestClient) -> None:
    data = client.get(
        f"/v1/derivations/{EXAMPLE_DERIVATION_ID}",
        params=[("include", "inputs"), ("include", "rules")],
    ).json()["data"]

    assert [ref["ref_id"] for ref in data["inputs"]] == [EXAMPLE_MANIFEST_ID]
    assert {rule["rule_id"] for rule in data["rules"]} == {
        "cr_nd_stream_vocab_1",
        "cr_nd_units_1",
    }


def test_an_unknown_derivation_is_not_found(client: TestClient) -> None:
    response = client.get("/v1/derivations/drv_nothinghere")

    assert response.status_code == 404
    assert response.json()["type"] == f"{TYPE_BASE}/not_found"


def test_the_manifest_is_the_terminal_record(client: TestClient) -> None:
    data = client.get(f"/v1/manifests/{EXAMPLE_MANIFEST_ID}").json()["data"]

    assert data["manifest_id"] == EXAMPLE_MANIFEST_ID
    assert data["source_id"] == "nd_mpr_xlsx"
    assert len(data["sha256"]) == 64
    assert data["acquisition_url"]
    assert data["superseded_by"] is None
    assert "storage_uri" in data


def test_the_bytes_route_is_gated_and_the_record_is_not(client: TestClient) -> None:
    """SB-07 §9.6, as written: the record is open to every key, the bytes are owner-scoped.

    This test previously asserted no `/bytes` route at all. That read §9.6's justification —
    verifiability is the checksum plus the acquisition URL — as if it forbade the route,
    when §9.6 specifies it and scopes it. S-K adds it; the gate is what §9.6 actually asks for.
    """
    document = client.get("/openapi.json").json()

    assert "/v1/manifests/{manifest_id}/bytes" in document["paths"]
    assert "forbidden" in str(document["paths"]["/v1/manifests/{manifest_id}/bytes"]["get"])


def test_the_manifest_collection_filters_by_source(client: TestClient) -> None:
    data = client.get("/v1/manifests", params={"source_id": "nd_gis_wells"}).json()["data"]

    assert {item["source_id"] for item in data} == {"nd_gis_wells"}


def test_the_manifest_collection_orders_newest_first(client: TestClient) -> None:
    data = client.get("/v1/manifests").json()["data"]

    fetched = [item["fetched_at"] for item in data]
    assert fetched == sorted(fetched, reverse=True)


def test_an_unknown_manifest_is_not_found(client: TestClient) -> None:
    assert client.get("/v1/manifests/man_nothing").status_code == 404


def test_the_prebuilt_explain_link_is_callable_verbatim(client: TestClient) -> None:
    """A cell handle carries `#`; unencoded, the rest is a fragment the server never receives."""
    body = client.get(f"/v1/wells/{EXAMPLE_API10}/production").json()
    link = body["links"]["explain"]

    assert "#" not in link
    chains = client.get(link).json()["data"]["chains"]
    assert {chain["handle"] for chain in chains} == set(body["data"]["_lineage"].values())
    assert all(chain["truncated"] is False for chain in chains)


def test_the_terminal_manifest_closes_the_chain_even_as_the_roots_direct_input(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    """DR-83: R2 says the chain terminates at a checksummed regulator file, and `nodes` must
    read that way. Discovery order put a root's direct manifest input mid-list — live ND served
    [promote, manifest, parse] and the drawer's bottom node was a derivation under a header
    claiming a terminal manifest. This chain reproduces that exact input ordering: the manifest
    is the root's first-ord input and a deeper derivation follows it."""
    manifest_id = seed_manifest(seeded, sha256="f" * 64, source_key="2026_07.xlsx")
    with lineage_session(
        recorder=PostgresRecorder(seeded),
        environment=FIXTURE_ENV,
        clock=FixedClock(),
        correlation_id="run_dr83",
    ), derive(
        "canonical.promote",
        output=OutputSpec(
            store="postgres",
            dataset="canonical.production_monthly",
            partition={"source_id": "nd_mpr_xlsx", "probe": "dr83"},
        ),
        params={"source_id": "nd_mpr_xlsx", "probe": "dr83"},
        inputs=[
            InputRef(
                kind="manifest", ref_id=manifest_id, role="primary", as_of_vintage=VINTAGE
            )
        ],
    ) as promote:
        with derive(
            "stage.parse",
            output=OutputSpec(store="postgres", dataset="staging.nd_mpr_oil"),
            params={"sheet": "Oil", "probe": "dr83"},
            inputs=[
                InputRef(
                    kind="manifest", ref_id=manifest_id, role="primary", as_of_vintage=VINTAGE
                )
            ],
        ) as parse:
            parse.set_output_hash("e" * 64)
        promote.set_output_hash("d" * 64)
    seeded.commit()

    chain = client.get(
        "/v1/explain", params={"h": promote.derivation_id, "depth": "full"}
    ).json()["data"]["chains"][0]
    types = [node["type"] for node in chain["nodes"]]

    assert len(chain["nodes"]) >= 3
    assert chain["nodes"][0]["id"] == promote.derivation_id
    assert chain["nodes"][-1]["type"] == "manifest"
    assert chain["nodes"][-1]["id"] in chain["terminals"]
    assert max(i for i, t in enumerate(types) if t == "derivation") < types.index("manifest")
