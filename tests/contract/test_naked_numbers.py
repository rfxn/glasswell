"""The R6 gate: SB-07 §10 checks 2 and 3, run over every operation the API serves.

Every numeric leaf of `data` is either an SB-07 §9.1(a) figure, covered by a §9.1(b)
`_lineage` sidecar, or exempted by `non_figure_allowlist.yml` with a written reason.
Every handle found is then resolved through `/v1/explain` to a terminal manifest.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi.testclient import TestClient

from glasswell.api.examples import DATASET_KEY, REQUEST_EXAMPLE_KEY
from glasswell.lineage.ids import parse_handle
from tests.contract.conftest import TX_API10

ALLOWLIST_PATH = Path(__file__).with_name("non_figure_allowlist.yml")
NUMERIC_TEXT = re.compile(r"\A-?\d+(\.\d+)?\Z")


def _allowlist() -> list[dict[str, str]]:
    entries = yaml.safe_load(ALLOWLIST_PATH.read_text(encoding="utf-8"))
    return list(entries or ())


def _pattern_regex(pattern: str) -> re.Pattern[str]:
    parts = []
    for token in pattern.split("/"):
        if token == "**":
            parts.append(".*")
        elif token == "*":
            parts.append("[^/]*")
        else:
            parts.append(re.escape(token))
    return re.compile("\\A" + "/".join(parts) + "\\Z")


ALLOWED = [(_pattern_regex(entry["pointer"]), entry) for entry in _allowlist()]


def _is_number(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return True
    return isinstance(value, str) and bool(NUMERIC_TEXT.match(value))


def _sidecar_prefixes(node: Any, pointer: str, found: set[str]) -> None:
    if isinstance(node, dict):
        for key in node.get("_lineage", {}):
            found.add(f"{pointer}/{key.replace('.', '/')}")
        for key, value in node.items():
            _sidecar_prefixes(value, f"{pointer}/{key}", found)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            _sidecar_prefixes(value, f"{pointer}/{index}", found)


def _covered_by_sidecar(pointer: str, prefixes: set[str]) -> bool:
    return any(pointer == prefix or pointer.startswith(prefix + "/") for prefix in prefixes)


def _allowed(pointer: str) -> bool:
    return any(regex.match(pointer) for regex, _ in ALLOWED)


def _walk(
    node: Any, pointer: str, prefixes: set[str], parent: Any, key: str
) -> Iterator[tuple[str, str]]:
    """Every numeric leaf, classified `figure`, `allowed` or `naked`."""
    if isinstance(node, dict):
        for child_key, value in node.items():
            yield from _walk(value, f"{pointer}/{child_key}", prefixes, node, child_key)
        return
    if isinstance(node, list):
        for index, value in enumerate(node):
            yield from _walk(value, f"{pointer}/{index}", prefixes, node, str(index))
        return
    if not _is_number(node):
        return
    in_figure = isinstance(parent, dict) and key == "value" and "d" in parent
    if in_figure or _covered_by_sidecar(pointer, prefixes):
        yield pointer, "figure"
    elif _allowed(pointer):
        yield pointer, "allowed"
    else:
        yield pointer, "naked"


def _classify(data: Any, wanted: str) -> list[str]:
    prefixes: set[str] = set()
    _sidecar_prefixes(data, "", prefixes)
    return [pointer for pointer, status in _walk(data, "", prefixes, None, "") if status == wanted]


def naked_numbers(data: Any) -> list[str]:
    return _classify(data, "naked")


def figure_numbers(data: Any) -> list[str]:
    """Numbers the response does carry lineage for — the population no exemption may cover."""
    return _classify(data, "figure")


def handles(data: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(data, dict):
        if isinstance(data.get("d"), str):
            found.add(data["d"])
        for key, value in data.items():
            if key == "_lineage" and isinstance(value, dict):
                found.update(str(handle) for handle in value.values())
            else:
                found.update(handles(value))
    elif isinstance(data, list):
        for value in data:
            found.update(handles(value))
    return found


# The published examples are all North Dakota, and a jurisdiction the walker never walks is a
# jurisdiction the R6 gate does not cover. These are the same operations against the TX well the
# fixture seeds: it is the only well with a depth figure, a null status and a production
# endpoint whose answer is a disclosure, so without them the walker has never seen a depth
# figure at all and MUST-KNOW-14's fixture reached no gate.
JURISDICTION_ARMS: tuple[tuple[str, dict[str, Any]], ...] = (
    ("get_well[tx]", {"url": f"/v1/wells/{TX_API10}", "params": {}}),
    ("get_well_production[tx]", {"url": f"/v1/wells/{TX_API10}/production", "params": {}}),
    ("list_wells[tx]", {"url": "/v1/wells", "params": {"county": "003"}}),
    (
        "get_conformance_rule[tx]",
        {"url": "/v1/conformance/cr_tx_allocation_scope_1", "params": {}},
    ),
)


def exercised(client: TestClient) -> list[tuple[str, dict[str, Any]]]:
    """Every operation, called with the example the OpenAPI document publishes, and every
    jurisdiction arm — because one example per operation is one jurisdiction per operation."""
    document = client.get("/openapi.json").json()
    calls = []
    for path, item in document["paths"].items():
        operation = item.get("get")
        if operation is None:
            continue
        example = operation[REQUEST_EXAMPLE_KEY]
        url = path
        for name, value in example.get("path", {}).items():
            url = url.replace("{" + name + "}", str(value))
        calls.append((operation["operationId"], {"url": url, "params": example.get("query", {})}))
    return [*calls, *JURISDICTION_ARMS]


def test_every_browsable_dataset_is_an_operation_the_walker_exercises(client: TestClient) -> None:
    """SB-08 §6.1: the catalogue is generated from operations, so it cannot outrun the R6 gate."""
    document = client.get("/openapi.json").json()
    declared = {
        operation["operationId"]
        for item in document["paths"].values()
        for operation in item.values()
        if isinstance(operation, dict) and DATASET_KEY in operation
    }

    assert declared
    assert declared <= {operation_id for operation_id, _ in exercised(client)}


def test_the_walker_reaches_a_depth_figure_and_a_second_jurisdiction(client: TestClient) -> None:
    """The gate's own coverage, asserted: a walker that only ever sees ND proves nothing about
    the TX surface, and `total_depth_ft` is null on every ND well."""
    walked = {operation_id for operation_id, _ in exercised(client)}
    assert {name for name in walked if name.endswith("[tx]")} == {
        name for name, _ in JURISDICTION_ARMS
    }

    figures = set()
    for _, call in exercised(client):
        if TX_API10 not in call["url"]:
            continue
        body = payload(client.get(call["url"], params=call["params"]))
        if body is not None:
            figures.update(figure_numbers(body))

    assert any(pointer.endswith("/total_depth_ft/value") for pointer in figures), (
        "the walker still never sees a depth figure, so R6 does not cover it"
    )


def test_the_allowlist_states_a_reason_for_every_exemption() -> None:
    assert ALLOWED
    assert all(entry.get("reason") for _, entry in ALLOWED)


def test_every_documented_example_is_callable(client: TestClient) -> None:
    failures = {
        operation_id: client.get(call["url"], params=call["params"]).status_code
        for operation_id, call in exercised(client)
    }

    assert {name: code for name, code in failures.items() if code != 200} == {}


def payload(response: Any) -> Any:
    """`data` for an enveloped response, the whole body for /healthz, None for a tile."""
    if not response.headers["content-type"].startswith("application/json"):
        return None
    body = response.json()
    return body.get("data", body) if isinstance(body, dict) else body


def test_no_served_number_is_naked(client: TestClient) -> None:
    offenders: dict[str, list[str]] = {}
    for operation_id, call in exercised(client):
        body = payload(client.get(call["url"], params=call["params"]))
        if body is None:
            continue
        found = naked_numbers(body)
        if found:
            offenders[operation_id] = found

    assert offenders == {}


def served_figures(client: TestClient) -> set[str]:
    figures: set[str] = set()
    for _, call in exercised(client):
        body = payload(client.get(call["url"], params=call["params"]))
        if body is not None:
            figures.update(figure_numbers(body))
    return figures


def test_no_exemption_covers_a_served_figure(client: TestClient) -> None:
    """The allowlist's minimality gate: `- pointer: /**` would silence every check above."""
    figures = served_figures(client)

    assert figures, "no operation served a figure, so this test proves nothing"
    covered = {
        entry["pointer"]: sorted(pointer for pointer in figures if regex.match(pointer))
        for regex, entry in ALLOWED
    }

    assert {pointer: hits for pointer, hits in covered.items() if hits} == {}


def test_no_number_is_naked_in_any_reachable_derivation(client: TestClient) -> None:
    """One published example per operation is not the surface. Every handle has a record too."""
    offenders: dict[str, list[str]] = {}
    for handle in sorted(walked_handles(client)):
        derivation = parse_handle(handle).derivation_id
        body = payload(
            client.get(f"/v1/derivations/{derivation}", params={"include": ["inputs", "rules"]})
        )
        found = naked_numbers(body)
        if found:
            offenders[derivation] = found

    assert offenders == {}


def walked_handles(client: TestClient) -> set[str]:
    found: set[str] = set()
    for _, call in exercised(client):
        body = payload(client.get(call["url"], params=call["params"]))
        if body is not None:
            found.update(handles(body))
    return found


def test_every_handle_resolves_to_a_terminal_manifest(client: TestClient) -> None:
    """SB-07 §10 check 3 at seeded scale — this is S9, and it is never cut."""
    found = walked_handles(client)

    assert found, "no response carried a handle, so the walker proves nothing"
    for handle in sorted(found):
        chain = client.get("/v1/explain", params={"h": handle, "depth": "full"}).json()
        resolved = chain["data"]["chains"][0]
        node_types = {node["id"]: node["type"] for node in resolved["nodes"]}
        assert resolved["truncated"] is False
        assert resolved["terminals"], f"{handle} resolves to no terminal"
        assert all(node_types[terminal] == "manifest" for terminal in resolved["terminals"])


@pytest.mark.parametrize(
    ("pointer", "expected"),
    [("/series/oil_bbl/0", True), ("/series/oil_bbl", True), ("/series/gas_mcf/0", False)],
)
def test_the_walker_reads_dotted_sidecar_paths(pointer: str, expected: bool) -> None:
    prefixes: set[str] = set()
    _sidecar_prefixes({"series": {"oil_bbl": [1]}, "_lineage": {"series.oil_bbl": "drv_x"}},
                      "", prefixes)

    assert _covered_by_sidecar(pointer, prefixes) is expected
