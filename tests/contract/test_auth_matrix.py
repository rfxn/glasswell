"""Every served endpoint against every principal class, as one table.

`qa-validation-report.md` §4 found MAJOR-2 and MAJOR-3 by walking the API three ways. This
is the auth half of that walk, committed so it runs on every push rather than when somebody
remembers to. The table is the contract: a new endpoint that is not in it fails
`test_the_matrix_covers_every_served_operation`, so the surface cannot grow past the gate.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from glasswell.api.csrf import CSRF_HEADER, SAFE_METHODS
from glasswell.api.deps import SESSION_COOKIE
from glasswell.api.examples import (
    EXAMPLE_API10,
    EXAMPLE_BBOX,
    EXAMPLE_DERIVATION_ID,
    EXAMPLE_ERROR_CODE,
    EXAMPLE_MANIFEST_ID,
    EXAMPLE_PUBLICATION_ID,
    EXAMPLE_QUARANTINE_ID,
    EXAMPLE_RULE_ID,
    EXAMPLE_TERM_ID,
    EXAMPLE_TILE,
    EXAMPLE_VINTAGE_ID,
)
from tests.contract.conftest import as_principal, challenge, issue_key

OPEN = "open"
READ = "read"
OWNER = "owner"
# A fourth class this track introduces. `read` means "any live credential"; these routes act
# on the caller's own session, so a key -- which has no session -- cannot reach them at all.
SESSION = "session"

TILE = EXAMPLE_TILE
_VINTAGE = "vin_nd_mpr_xlsx_2026-08-01"

# (method, path, class). `open` needs no credential; `read` is any live credential; `owner`
# is owner scope, held by the owner key or an owner account; `session` is a route that acts on
# the caller's own session and is therefore unreachable with a key.
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
    ("GET", f"/v1/wells/{EXAMPLE_API10}/type-curve", READ),
    ("GET", f"/v1/wells/{EXAMPLE_API10}/type-curve?explain=true&explain_depth=8", READ),
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
    ("GET", "/v1/type-curves", READ),
    ("GET", "/v1/type-curves?explain=true", READ),
    ("GET", "/v1/modeling/publications", READ),
    ("GET", f"/v1/modeling/publications/{EXAMPLE_PUBLICATION_ID}", READ),
    ("GET", f"/v1/modeling/publications/{EXAMPLE_PUBLICATION_ID}?explain=true", READ),
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
    ("GET", "/v1/session/challenge", OPEN),
    ("POST", "/v1/session", OPEN),
    # OPEN, deliberately. "Who am I" is not a privileged question and `nobody` is a valid
    # answer; it discloses strictly less than /v1/session/challenge, which already mints a
    # signed token for an uncredentialled caller. Gated, the ordinary first visit to a public
    # instance was a console error and a failed request on every page load.
    ("GET", "/v1/session", OPEN),
    ("DELETE", "/v1/session", SESSION),
    ("POST", "/v1/session/password", SESSION),
    ("GET", "/v1/users", OWNER),
    ("POST", "/v1/users", OWNER),
    ("PATCH", "/v1/users/{user_id}", OWNER),
    ("DELETE", "/v1/users/{user_id}", OWNER),
    ("POST", "/v1/users/{user_id}/password", OWNER),
    # Finding F-2: both were anonymous, and the coverage test below could not see it
    # because it walked document["paths"], which neither path is an entry in.
    ("GET", "/docs", READ),
    ("GET", "/openapi.json", READ),
)

# Routes exercised for coverage but deliberately excluded from the status assertions: the
# two open session routes need a request body or a pre-session cookie to answer anything
# other than a refusal, and they have dedicated files.
NOT_STATUS_PROBED = frozenset(
    {
        # Needs a pre-session cookie and a body; test_login_uniformity.py owns it.
        ("POST", "/v1/session"),
        # Needs the current password in the body; test_session_cookie.py owns it.
        ("POST", "/v1/session/password"),
        # Need a body and a target account; test_users.py and test_users_surface.py own them.
        ("POST", "/v1/users"),
        ("PATCH", "/v1/users/{user_id}"),
        ("DELETE", "/v1/users/{user_id}"),
        ("POST", "/v1/users/{user_id}/password"),
    }
)

SESSION_PRINCIPALS = ("owner_session", "viewer_session")

PRINCIPALS = (
    "anonymous",
    "invalid",
    "revoked",
    "guest",
    "agent",
    "owner",
    "owner_session",
    "viewer_session",
    "expired_session",
)
CREDENTIALLED = ("guest", "agent", "owner", "owner_session", "viewer_session")
DENIED = ("anonymous", "invalid", "revoked", "expired_session")

ISSUE_BODY = {"label": "matrix-probe-2026", "scope": "guest"}


def _expected(access: str, principal: str) -> str:
    """`allow` or `deny`. Statuses are asserted separately so a 500 cannot read as a deny."""
    if access == OPEN:
        return "allow"
    if principal in DENIED:
        return "deny"
    if access == SESSION:
        return "allow" if principal in SESSION_PRINCIPALS else "deny"
    if access == OWNER:
        return "allow" if principal in ("owner", "owner_session") else "deny"
    return "allow"


@pytest.fixture
def principals(
    client: TestClient,
    owner_session: TestClient,
    viewer_session: TestClient,
    expired_session: TestClient,
) -> dict[str, TestClient]:
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
        "owner_session": owner_session,
        "viewer_session": viewer_session,
        "expired_session": expired_session,
    }


def _call(caller: TestClient, method: str, path: str, owner: TestClient) -> int:
    if "{key_id}" in path:
        issued = owner.post(
            "/v1/keys", json={**ISSUE_BODY, "label": f"matrix-{abs(hash(path)) % 9999}-2026"}
        )
        path = path.replace("{key_id}", issued.json()["data"]["key_id"])
    headers = _csrf_headers(caller, method)
    if method == "POST":
        return caller.post(path, json=ISSUE_BODY, headers=headers).status_code
    if method == "DELETE":
        return caller.delete(path, headers=headers).status_code
    return caller.get(path).status_code


def _csrf_headers(caller: TestClient, method: str) -> dict[str, str]:
    """A session making a state-changing call carries a CSRF token, as a browser would.

    Without this the matrix would read every session mutation as a refusal and hide whatever
    the authorization answer actually is.
    """
    if method in SAFE_METHODS or not caller.cookies.get(SESSION_COOKIE):
        return {}
    return {CSRF_HEADER: challenge(caller)}


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
    if (method, path) in NOT_STATUS_PROBED:
        pytest.skip("needs a request body and a pre-session cookie; covered by its own file")
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


def reachable_routes(app) -> set[tuple[str, str]]:
    """Every route the app will actually answer, including those outside the OpenAPI document.

    `app.routes` holds lazily-expanded `_IncludedRouter` objects in this FastAPI version, so
    walking it naively sees only the two hand-registered routes. `effective_route_contexts()`
    is what flattens them.
    """
    found: set[tuple[str, str]] = set()
    for route in app.routes:
        contexts = getattr(route, "effective_route_contexts", None)
        if contexts is None:
            path, methods = getattr(route, "path", None), getattr(route, "methods", None)
            if path and methods:
                found.update((method, path) for method in methods)
            continue
        for context in contexts():
            found.update((method, context.path) for method in context.methods or ())
    return {(method, path) for method, path in found if method != "HEAD"}


def test_the_matrix_covers_every_reachable_route(client: TestClient) -> None:
    """Finding F-2's control, and the reason it is not the test below.

    `/docs` and `/openapi.json` were served anonymously, and no walk of `document["paths"]`
    could ever have caught it, because neither path is an entry there. This walks what the
    router will answer instead, so a route that is reachable but undeclared fails here.
    """
    covered = {(method, _template(path.split("?")[0])) for method, path, _ in MATRIX}

    uncovered = reachable_routes(client.app) - covered

    assert uncovered == set(), f"reachable with no auth answer in the matrix: {sorted(uncovered)}"


def test_the_coverage_walk_sees_past_the_openapi_document(client: TestClient) -> None:
    """The blind spot, asserted directly: these two are reachable and are not in `paths`."""
    document = client.get("/openapi.json").json()
    declared = {path for path in document["paths"]}
    walked = {path for _, path in reachable_routes(client.app)}

    assert "/docs" not in declared
    assert "/openapi.json" not in declared
    assert {"/docs", "/openapi.json"} <= walked


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
        (EXAMPLE_PUBLICATION_ID, "publication_id"),
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

    assert reachable is (principal in ("owner", "owner_session"))


@pytest.mark.parametrize("principal", CREDENTIALLED)
def test_no_principal_class_can_reach_user_management_except_the_owner(
    principals: dict[str, TestClient], principal: str
) -> None:
    """The same hard line as key management, asserted outside the table so it cannot be
    edited away by a matrix row."""
    reachable = principals[principal].get("/v1/users").status_code == 200

    assert reachable is (principal in ("owner", "owner_session"))


def test_the_document_routes_are_gated_in_the_deployed_shape(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The matrix builds an app with no SPA mount; production always has one.

    `Mount("/")` shadows anything registered after it, so with `GLASSWELL_WEB_ROOT` set --
    which is the deployed configuration -- `/docs` and `/openapi.json` answered 404 rather
    than the gate. Fail-closed, but it made the F-2 fix real in code and vacuous on the host,
    and it would have failed four verify/smoke assertions on the deploy gate.
    """
    from glasswell.api import create_app
    from glasswell.api.deps import WEB_ROOT_ENV

    (tmp_path / "index.html").write_text("<html></html>", encoding="utf-8")
    monkeypatch.setenv(WEB_ROOT_ENV, str(tmp_path))

    with TestClient(create_app()) as deployed:
        for path in ("/docs", "/openapi.json"):
            status = deployed.get(path).status_code

            assert status == 403, f"{path} answered {status}; the SPA mount shadows the gate"


def test_the_open_surface_is_exactly_the_ruled_set(client: TestClient) -> None:
    """O-2 chose Option A -- closed by default -- so the anonymous surface is a decision, not
    an accident. Anything reachable without a credential must be listed here on purpose.

    `GET /v1/session` is on this list and was not in O-2's original enumeration. It answers
    only about the caller itself, cannot enumerate accounts, and discloses less than the
    challenge route beside it; gated, it made every first page load on a public instance emit
    a console error and a failed request.
    """
    expected = {
        ("GET", "/healthz"),
        ("GET", "/v1/session/challenge"),
        ("POST", "/v1/session"),
        ("GET", "/v1/session"),
    }

    served_open = {
        (method, path.split("?")[0]) for method, path, access in MATRIX if access == OPEN
    }

    assert served_open == expected, "the anonymous surface changed without a ruling"
