from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from typing import Any

import psycopg
from fastapi.testclient import TestClient

from glasswell.api.examples import EXAMPLE_API10, EXAMPLE_BBOX, EXAMPLE_PUBLICATION_ID
from glasswell.lineage.capture import derive, lineage_session
from glasswell.lineage.ids import parse_handle
from glasswell.lineage.models import OutputSpec
from glasswell.lineage.store import PostgresRecorder
from tests.contract.conftest import TX_API10
from tests.support.seed import FIXTURE_ENV, seed_well


def _handles(node: Any) -> Iterable[str]:
    if isinstance(node, dict):
        handle = node.get("d")
        if isinstance(handle, str):
            yield handle
        lineage = node.get("_lineage")
        if isinstance(lineage, dict):
            yield from (value for value in lineage.values() if isinstance(value, str))
        for value in node.values():
            yield from _handles(value)
    elif isinstance(node, list):
        for value in node:
            yield from _handles(value)


def _strict_explain(client: TestClient, handle: str):
    return client.get("/v1/explain", params={"h": handle, "depth": "full"})


def test_every_selector_bearing_surface_resolves_through_a_registered_profile(
    client: TestClient,
) -> None:
    calls = (
        (f"/v1/wells/{TX_API10}", {}),
        (f"/v1/wells/{EXAMPLE_API10}/production", {}),
        (f"/v1/wells/{EXAMPLE_API10}/production/pools", {}),
        (f"/v1/wells/{EXAMPLE_API10}/completions", {}),
        (f"/v1/wells/{EXAMPLE_API10}/neighbors", {}),
        ("/v1/wells/status-summary", {"bbox": EXAMPLE_BBOX}),
        (f"/v1/wells/{EXAMPLE_API10}/type-curve", {}),
        ("/v1/type-curves", {}),
        (f"/v1/modeling/publications/{EXAMPLE_PUBLICATION_ID}", {}),
    )
    found: set[str] = set()
    for path, params in calls:
        response = client.get(path, params=params)
        assert response.status_code == 200, response.text
        found.update(_handles(response.json()["data"]))

    assert found
    for handle in sorted(found):
        response = _strict_explain(client, handle)
        assert response.status_code == 200, (handle, response.text)


def test_direct_and_request_computed_figures_name_the_honest_output_dataset(
    client: TestClient, db: psycopg.Connection
) -> None:
    well = client.get(f"/v1/wells/{TX_API10}").json()["data"]
    summary = client.get("/v1/wells/status-summary", params={"bbox": EXAMPLE_BBOX}).json()["data"]
    roots = {
        "total_depth": parse_handle(well["total_depth_ft"]["d"]).derivation_id,
        "lateral_length": parse_handle(
            client.get(f"/v1/wells/{EXAMPLE_API10}").json()["data"]["lateral_length_ft"]["d"]
        ).derivation_id,
        "status_count": parse_handle(summary["wells"]["d"]).derivation_id,
        "type_curve": parse_handle(
            client.get(f"/v1/wells/{EXAMPLE_API10}/type-curve").json()["data"]["_lineage"][
                "series.monthly_p50"
            ]
        ).derivation_id,
    }

    with db.cursor() as cursor:
        cursor.execute(
            "select derivation_id, operation, output_dataset, output_store, params"
            " from lineage.derivations where derivation_id = any(%s)",
            (list(roots.values()),),
        )
        rows = {row[0]: row[1:] for row in cursor.fetchall()}

    assert rows[roots["total_depth"]][0:3] == (
        "canonical.promote",
        "canonical.wells",
        "postgres",
    )
    for name, dataset in (
        ("lateral_length", "api.well_detail"),
        ("status_count", "api.well_status_summary"),
        ("type_curve", "api.type_curve"),
    ):
        operation, output_dataset, store, params = rows[roots[name]]
        assert (operation, output_dataset, store) == ("api.respond", dataset, "response")
        assert params["operation_id"] in {
            "get_well",
            "get_well_status_summary",
            "get_well_type_curve",
        }
        with db.cursor() as cursor:
            cursor.execute(
                "select count(*) from lineage.response_selector_outputs"
                " where derivation_id = %s",
                (roots[name],),
            )
            assert cursor.fetchone()[0] > 0

    with db.cursor() as cursor:
        cursor.execute(
            "select rule_id from lineage.derivation_rules where derivation_id = %s",
            (roots["status_count"],),
        )
        rules = {row[0] for row in cursor.fetchall()}
    assert "cr_nd_geometry_provenance_1" in rules
    assert "cr_nd_status_vocab_1" in rules

    # The served curve's response derivation cites the pinned typecurve.build derivation as an
    # input, which is the whole of "no figure reads an unregistered artifact" seen from outside.
    control = client.get(
        f"/v1/modeling/publications/{EXAMPLE_PUBLICATION_ID}"
    ).json()["data"]["derivations"]["type_curve"]
    with db.cursor() as cursor:
        cursor.execute(
            "select ref_id from lineage.derivation_inputs where derivation_id = %s",
            (roots["type_curve"],),
        )
        assert control in {row[0] for row in cursor.fetchall()}


def test_an_unregistered_derivation_output_is_strictly_refused(
    client: TestClient, db: psycopg.Connection
) -> None:
    with (
        lineage_session(
            recorder=PostgresRecorder(db),
            environment=FIXTURE_ENV,
            correlation_id="run_unregistered_selector_contract",
        ),
        derive(
            "canonical.promote",
            output=OutputSpec(store="postgres", dataset="canonical.unregistered_output"),
            params={"fixture": "selector_fail_closed"},
        ) as context,
    ):
        context.set_output_hash("f0" * 32)
        context.set_rows(1)
    db.commit()

    response = _strict_explain(client, f"{context.derivation_id}#col=value")

    assert response.status_code == 422
    assert response.json()["type"].endswith("/selector_ambiguous")
    assert "no unique registered selector profile" in response.json()["detail"]


def test_inline_explain_warns_but_standalone_explain_remains_strict(
    client: TestClient, db: psycopg.Connection
) -> None:
    with db.cursor() as cursor:
        cursor.execute(
            "delete from lineage.selector_output_registry"
            " where operation = 'canonical.promote' and output_dataset = 'canonical.wells'"
        )
    db.commit()

    response = client.get(f"/v1/wells/{TX_API10}", params={"explain": "true"})

    assert response.status_code == 200, response.text
    body = response.json()
    warning = next(
        item for item in body["meta"]["warnings"] if item["code"] == "explain_invalid_selector"
    )
    depth_handle = body["data"]["total_depth_ft"]["d"]
    assert depth_handle in warning["detail"]
    assert depth_handle not in body["_explain"]
    assert _strict_explain(client, depth_handle).status_code == 422


def test_completion_pool_selector_requires_exactly_one_time_key(client: TestClient) -> None:
    data = client.get(f"/v1/wells/{EXAMPLE_API10}/completions").json()["data"]
    handle = next(
        value for pool in data["pools"] for value in pool["_lineage"].values() if "&pm=" in value
    )
    derivation_id, selector = handle.split("#", 1)
    without_time = "&".join(term for term in selector.split("&") if not term.startswith("pm="))

    neither = _strict_explain(client, f"{derivation_id}#{without_time}")
    both = _strict_explain(client, f"{handle}&effective_from=2026-01-01")

    assert neither.status_code == 422
    assert both.status_code == 422
    assert "exactly one time key" in neither.json()["detail"]
    assert "exactly one time key" in both.json()["detail"]


def test_unsafe_status_values_get_distinct_canonical_selectors(
    client: TestClient, db: psycopg.Connection
) -> None:
    with db.cursor() as cursor:
        cursor.execute(
            "select api10, source_manifest_id, derivation_id from canonical.wells_latest"
            " where api10 in (%s, %s) order by api10",
            (EXAMPLE_API10, TX_API10),
        )
        sources = {row[0]: row[1:] for row in cursor.fetchall()}
    for api10, status, overrides in (
        (EXAMPLE_API10, "A B", {}),
        (
            TX_API10,
            "A?B",
            {"state_code": "42", "basin": "permian", "well_type_reported": "PRODUCING"},
        ),
    ):
        manifest_id, derivation_id = sources[api10]
        seed_well(
            db,
            api10=api10,
            effective_from=date(2026, 8, 2),
            manifest_id=manifest_id,
            derivation_id=derivation_id,
            status_canonical=status,
            **overrides,
        )
    db.commit()

    statuses = client.get("/v1/wells/status-summary", params={"bbox": "-105,30,-100,50"}).json()[
        "data"
    ]["statuses"]
    handles = [row["wells"]["d"] for row in statuses]

    assert {row["status"] for row in statuses} == {"A B", "A?B"}
    assert len(set(handles)) == 2
    assert all("status_b64=" in handle for handle in handles)
    encoded = [
        next(
            term.split("=", 1)[1]
            for term in str(parse_handle(handle).selector).split("&")
            if term.startswith("status_b64=")
        )
        for handle in handles
    ]
    assert all(character not in "".join(encoded) for character in "+/=")
