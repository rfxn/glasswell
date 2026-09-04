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
from glasswell.api.routers import validators
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


def _is_handle(value: Any) -> bool:
    """A handle is a non-empty string. `d: null` is a key, not a derivation."""
    return isinstance(value, str) and bool(value)


def _sidecar_prefixes(node: Any, pointer: str, found: set[str]) -> None:
    if isinstance(node, dict):
        for key, handle in node.get("_lineage", {}).items():
            if _is_handle(handle):
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
    # The value of `d`, not its presence: a figure whose handle is null resolves to nothing, so
    # classifying it as covered would let the whole surface go handleless with the gate green.
    in_figure = isinstance(parent, dict) and key == "value" and _is_handle(parent.get("d"))
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


def allowed_numbers(data: Any) -> list[str]:
    """Numbers an allowlist entry exempts — the population SB-08 A-2's register must explain."""
    return _classify(data, "allowed")


def handles(data: Any) -> set[str]:
    """The resolvable handles. Anything at a handle position that is not one is not silently
    dropped here — `unusable_handles` reports it, and the walker calls its figure naked."""
    found, _ = _handle_walk(data, "")
    return found


def unusable_handles(data: Any) -> list[str]:
    """Pointers where a handle is advertised and something unresolvable is served instead."""
    _, offenders = _handle_walk(data, "")
    return offenders


def _handle_walk(data: Any, pointer: str) -> tuple[set[str], list[str]]:
    found: set[str] = set()
    offenders: list[str] = []

    def collect(value: Any, at: str) -> None:
        if _is_handle(value):
            found.add(value)
        else:
            offenders.append(at)

    if isinstance(data, dict):
        if "d" in data:
            collect(data["d"], f"{pointer}/d")
        for key, value in data.items():
            if key == "_lineage" and isinstance(value, dict):
                for name, handle in value.items():
                    collect(handle, f"{pointer}/_lineage/{name}")
            else:
                nested, nested_offenders = _handle_walk(value, f"{pointer}/{key}")
                found |= nested
                offenders.extend(nested_offenders)
    elif isinstance(data, list):
        for index, value in enumerate(data):
            nested, nested_offenders = _handle_walk(value, f"{pointer}/{index}")
            found |= nested
            offenders.extend(nested_offenders)
    return found, offenders


# The published examples are all North Dakota, and a jurisdiction the walker never walks is a
# jurisdiction the R6 gate does not cover. These are the same operations against the TX well the
# fixture seeds: it is the only well with a depth figure and a production endpoint whose answer
# is a disclosure, so without them the walker has never seen a depth figure at all and
# MUST-KNOW-14's fixture reached no gate. It carries a status, `active` -- a well with none is
# `seed_statusless_well`, which a test seeds when it wants that absence.
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


def test_the_example_heuristic_cites_the_gate_that_holds_it_to_answering() -> None:
    """`_example_jurisdiction()` picks the served example by a structural heuristic and cites a
    gate as its justification, so the citation is load-bearing rather than decorative. It named
    `test_openapi_examples.py`, whose eight tests all read `/openapi.json` and call no route;
    the net that would redden on a wrongly-picked jurisdiction is the test above (gate-tx D-2).
    """
    source = Path(validators.__file__).read_text(encoding="utf-8")
    justification = source[: source.index("def _example_jurisdiction")]

    assert Path(__file__).name in justification
    assert "test_every_documented_example_is_callable" in justification


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


def test_no_served_handle_is_advertised_and_unresolvable(client: TestClient) -> None:
    """`d` present with a null or non-string value is the shape a presence check cannot see:
    every figure carries the key, nothing carries a derivation, and R6 reads as satisfied."""
    offenders: dict[str, list[str]] = {}
    carriers = 0
    for operation_id, call in exercised(client):
        body = payload(client.get(call["url"], params=call["params"]))
        if body is None:
            continue
        carriers += len(handles(body))
        found = unusable_handles(body)
        if found:
            offenders[operation_id] = found

    assert carriers, "no response carried a handle, so this test cannot fail"
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
    unreachable: dict[str, int] = {}
    walked = sorted(walked_handles(client))
    assert walked, "no response carried a handle, so this walk proves nothing"
    for handle in walked:
        derivation = parse_handle(handle).derivation_id
        response = client.get(
            f"/v1/derivations/{derivation}", params={"include": ["inputs", "rules"]}
        )
        # A problem body is application/problem+json, which `payload` reads as None and
        # `naked_numbers` reads as no offenders. Without this a 404 on a handle-derived id
        # is indistinguishable from a clean record (F14).
        if response.status_code != 200:
            unreachable[derivation] = response.status_code
            continue
        found = naked_numbers(payload(response))
        if found:
            offenders[derivation] = found

    assert unreachable == {}
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
        response = client.get("/v1/explain", params={"h": handle, "depth": "full"})
        assert response.status_code == 200, f"{handle} does not resolve: {response.text}"
        resolved = response.json()["data"]["chains"][0]
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
