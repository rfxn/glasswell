"""Every served endpoint against every principal class, as one table.

`qa-validation-report.md` §4 found MAJOR-2 and MAJOR-3 by walking the API three ways. This
is the auth half of that walk, committed so it runs on every push rather than when somebody
remembers to. The table is the contract: a new endpoint that is not in it fails
`test_the_matrix_covers_every_served_operation`, so the surface cannot grow past the gate.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from glasswell.api.examples import (
    EXAMPLE_API10,
    EXAMPLE_BBOX,
    EXAMPLE_DERIVATION_ID,
    EXAMPLE_ERROR_CODE,
    EXAMPLE_MANIFEST_ID,
    EXAMPLE_QUARANTINE_ID,
    EXAMPLE_RULE_ID,
    EXAMPLE_TERM_ID,
    EXAMPLE_TILE,
    EXAMPLE_VINTAGE_ID,
)
from tests.contract.conftest import as_principal, issue_key

OPEN = "open"
READ = "read"
OWNER = "owner"

TILE = EXAMPLE_TILE
_VINTAGE = "vin_nd_mpr_xlsx_2026-08-01"

# (method, path, class). `open` needs no credential; `read` is any live key; `owner` is the
# owner key alone. There is no fourth answer in this slice — every gate is one of the three.
MATRIX: tuple[tuple[str, str, str], ...] = (
    ("GET", "/healthz", OPEN),
    ("GET", "/v1", READ),
    ("GET", "/v1/health", READ),
    ("GET", "/v1/status", READ),
    ("GET", f"/v1/errors/{EXAMPLE_ERROR_CODE}", READ),
    ("GET", "/v1/wells", READ),
    ("GET", f"/v1/wells/status-summary?bbox={EXAMPLE_BBOX}", READ),
    ("GET", f"/v1/wells/{EXAMPLE_API10}", READ),
    ("GET", f"/v1/wells/{EXAMPLE_API10}/completions", READ),
    ("GET", f"/v1/wells/{EXAMPLE_API10}/neighbors", READ),
    ("GET", f"/v1/wells/{EXAMPLE_API10}/production", READ),
    ("GET", f"/v1/wells/{EXAMPLE_API10}/production/pools", READ),
    # DR-63/DR-64 add parameters, never gates: an optional flag that carried its own auth
    # answer would be a second access rule on a surface this table already covers, and it
    # would be invisible here because the table keys on the path.
    ("GET", f"/v1/wells/status-summary?bbox={EXAMPLE_BBOX}&explain=true", READ),
    ("GET", f"/v1/wells/{EXAMPLE_API10}?explain=true&explain_depth=8", READ),
    ("GET", f"/v1/wells/{EXAMPLE_API10}/completions?explain=true", READ),
    ("GET", f"/v1/wells/{EXAMPLE_API10}/neighbors?explain=true", READ),
    ("GET", f"/v1/wells/{EXAMPLE_API10}/production?explain=true", READ),
    ("GET", f"/v1/wells/{EXAMPLE_API10}/production/pools?explain=true", READ),
    ("GET", f"/v1/derivations/{EXAMPLE_DERIVATION_ID}?explain=true&explain_depth=8", READ),
    ("GET", "/v1/vintages?explain=true", READ),
    ("GET", f"/v1/vintages/{_VINTAGE}?explain=true", READ),
    ("GET", f"/v1/explain?h={EXAMPLE_DERIVATION_ID}", READ),
    ("GET", f"/v1/explain?h={EXAMPLE_DERIVATION_ID}&format=dot", READ),
    ("GET", "/v1/derivations", READ),
    ("GET", f"/v1/derivations/{EXAMPLE_DERIVATION_ID}", READ),
    ("GET", "/v1/manifests", READ),
    ("GET", f"/v1/manifests/{EXAMPLE_MANIFEST_ID}", READ),
    ("GET", f"/v1/manifests/{EXAMPLE_MANIFEST_ID}/bytes", OWNER),
    ("GET", "/v1/vintages", READ),
    ("GET", f"/v1/vintages/{_VINTAGE}", READ),
    ("GET", "/v1/conformance", READ),
    ("GET", f"/v1/conformance/{EXAMPLE_RULE_ID}", READ),
    ("GET", "/v1/quarantine", READ),
    ("GET", "/v1/quarantine/summary", READ),
    ("GET", f"/v1/quarantine/{EXAMPLE_QUARANTINE_ID}", READ),
    ("GET", "/v1/glossary", READ),
    ("GET", "/v1/formations", READ),
    ("GET", "/v1/glossary/index", READ),
    ("GET", f"/v1/glossary/{EXAMPLE_TERM_ID}", READ),
    ("GET", f"/v1/tiles/{TILE['layer']}/{TILE['z']}/{TILE['x']}/{TILE['y']}.pbf", READ),
    ("GET", "/v1/keys", OWNER),
    ("POST", "/v1/keys", OWNER),
    ("DELETE", "/v1/keys/{key_id}", OWNER),
    ("POST", "/v1/keys/{key_id}/rotate", OWNER),
)

PRINCIPALS = ("anonymous", "invalid", "revoked", "guest", "agent", "owner")
CREDENTIALLED = ("guest", "agent", "owner")

ISSUE_BODY = {"label": "matrix-probe-2026", "scope": "guest"}


def _expected(access: str, principal: str) -> str:
    """`allow` or `deny`. Statuses are asserted separately so a 500 cannot read as a deny."""
    if access == OPEN:
        return "allow"
    if principal in ("anonymous", "invalid", "revoked"):
        return "deny"
    if access == OWNER:
        return "allow" if principal == "owner" else "deny"
    return "allow"


@pytest.fixture
def principals(client: TestClient) -> dict[str, TestClient]:
    """One client per class, each holding a credential issued through the API itself."""
    revoked_secret = issue_key(client, label="matrix-revoked-2026", scope="agent")
    revoked_id = next(
        row["key_id"]
        for row in client.get("/v1/keys").json()["data"]
        if row["label"] == "matrix-revoked-2026"
    )
    client.delete(f"/v1/keys/{revoked_id}")
    return {
        "anonymous": as_principal(client, None),
        "invalid": as_principal(client, "a-key-that-was-never-issued"),
        "revoked": as_principal(client, revoked_secret),
        "guest": as_principal(client, issue_key(client, label="matrix-guest-2026", scope="guest")),
        "agent": as_principal(client, issue_key(client, label="matrix-agent-2026", scope="agent")),
        "owner": client,
    }


def _call(caller: TestClient, method: str, path: str, owner: TestClient) -> int:
    if "{key_id}" in path:
        issued = owner.post(
            "/v1/keys", json={**ISSUE_BODY, "label": f"matrix-{abs(hash(path)) % 9999}-2026"}
        )
        path = path.replace("{key_id}", issued.json()["data"]["key_id"])
    if method == "POST":
        return caller.post(path, json=ISSUE_BODY).status_code
    if method == "DELETE":
        return caller.delete(path).status_code
    return caller.get(path).status_code


@pytest.mark.parametrize(("method", "path", "access"), MATRIX, ids=lambda value: str(value))
@pytest.mark.parametrize("principal", PRINCIPALS)
def test_the_auth_matrix_holds(
    client: TestClient,
    principals: dict[str, TestClient],
    method: str,
    path: str,
    access: str,
    principal: str,
) -> None:
    status = _call(principals[principal], method, path, client)

    if _expected(access, principal) == "deny":
        assert status == 403, f"{principal} reached {method} {path}"
    else:
        assert status < 400, f"{principal} was refused {method} {path} with {status}"


@pytest.mark.parametrize("principal", ["anonymous", "invalid", "revoked"])
def test_a_refusal_names_the_right_reason(
    principals: dict[str, TestClient], principal: str
) -> None:
    """Three different failures, three different codes, all the same status and no oracle."""
    expected = {
        "anonymous": "key_required",
        "invalid": "unauthenticated",
        "revoked": "key_revoked",
    }[principal]

    body = principals[principal].get("/v1/health").json()

    assert body["type"] == f"/v1/errors/{expected}"


def test_the_matrix_covers_every_served_operation(client: TestClient) -> None:
    """A new endpoint arrives with an auth answer, or it does not arrive."""
    document = client.get("/openapi.json").json()
    served = {
        (method.upper(), path)
        for path, operations in document["paths"].items()
        for method in operations
    }
    covered = {(method, path.split("?")[0]) for method, path, _ in MATRIX}
    templated = {(method, _template(path)) for method, path in served}

    assert templated - {(method, _template(path)) for method, path in covered} == set()


def _template(path: str) -> str:
    """Collapse a concrete example id back onto the path template it came from."""
    for value, name in (
        (EXAMPLE_API10, "api10"),
        (EXAMPLE_DERIVATION_ID, "derivation_id"),
        (EXAMPLE_MANIFEST_ID, "manifest_id"),
        (EXAMPLE_QUARANTINE_ID, "quarantine_id"),
        (EXAMPLE_RULE_ID, "rule_id"),
        (EXAMPLE_TERM_ID, "term"),
        (EXAMPLE_ERROR_CODE, "code"),
        (_VINTAGE, "vintage_id"),
        (EXAMPLE_VINTAGE_ID, "vintage_id"),
    ):
        path = path.replace(value, "{" + name + "}")
    tile = f"/v1/tiles/{TILE['layer']}/{TILE['z']}/{TILE['x']}/{TILE['y']}.pbf"
    return "/v1/tiles/{layer}/{z}/{x}/{y}.pbf" if path == tile else path


@pytest.mark.parametrize("principal", CREDENTIALLED)
def test_no_principal_class_can_reach_key_management_except_the_owner(
    principals: dict[str, TestClient], principal: str
) -> None:
    """DR-67's hard line, asserted separately from the table so it cannot be edited away."""
    reachable = principals[principal].get("/v1/keys").status_code == 200

    assert reachable is (principal == "owner")
