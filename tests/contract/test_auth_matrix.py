"""Every served endpoint against every principal class, as one table.

`qa-validation-report.md` §4 found MAJOR-2 and MAJOR-3 by walking the API three ways. This
is the auth half of that walk, committed so it runs on every push rather than when somebody
remembers to. The table is the contract: a new endpoint that is not in it fails
`test_the_matrix_covers_every_served_operation`, so the surface cannot grow past the gate.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, NamedTuple

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
    KEY_HEADER,
)
from glasswell.api.routers.validators import EXAMPLE_JURISDICTION
from tests.contract.conftest import (
    OWNER_PASSWORD,
    SESSION_BASE_URL,
    VIEWER_PASSWORD,
    VIEWER_USERNAME,
    as_principal,
    challenge,
    issue_key,
)

OPEN = "open"
READ = "read"
OWNER = "owner"
# A fourth class this track introduces. `read` means "any live credential"; these routes act
# on the caller's own session, so a key -- which has no session -- cannot reach them at all.
SESSION = "session"

TILE = EXAMPLE_TILE
# A registered job the seed always writes, so the matrix names a row rather than a guess.
EXAMPLE_JOB_ID = "ingest_nd_gis"
_VINTAGE = "vin_nd_mpr_xlsx_2026-08-01"

ISSUE_BODY = {"label": "matrix-probe-2026", "scope": "guest"}
NEW_PASSWORD = "a-sufficiently-long-new-password"
WRONG_PASSWORD = "not-this-accounts-current-password"
CREATE_USER_BODY = {"username": "matrix-created", "password": NEW_PASSWORD, "role": "viewer"}
PROBE_USER_BODY = {"username": "matrix-target", "password": NEW_PASSWORD, "role": "viewer"}
# `seed_session` hashes it once per session, so a login the matrix expects to succeed costs
# no Argon2id work of its own.
LOGIN_BODY = {"username": VIEWER_USERNAME, "password": VIEWER_PASSWORD}
LOGIN = ("POST", "/v1/session")
# The account whose session the `{session_id}` probe is aimed at: seeded by the fixture below,
# revoked, and held by no principal the table admits.
PROBE_SESSION_USERNAME = "expired-session"
SESSION_PASSWORD = {"owner_session": OWNER_PASSWORD, "viewer_session": VIEWER_PASSWORD}


def _own_password_body(principal: str) -> dict[str, Any]:
    """The current password is the acting account's, so it is the principal that decides it."""
    return {
        "current_password": SESSION_PASSWORD.get(principal, WRONG_PASSWORD),
        "new_password": NEW_PASSWORD,
    }


# A body is a dict, or a function of the principal when the right value differs by caller.
Body = dict[str, Any] | Callable[[str], dict[str, Any]] | None


class Case(NamedTuple):
    method: str
    path: str
    access: str
    body: Body = None


# (method, path, class[, body]). `open` needs no credential; `read` is any live credential;
# `owner` is owner scope, held by the owner key or an owner account; `session` is a route that
# acts on the caller's own session and is therefore unreachable with a key. The fourth element
# is the request body, on the routes that need one to be dispatched at all.
MATRIX: tuple[tuple, ...] = (
    ("GET", "/healthz", OPEN),
    ("GET", "/v1", READ),
    ("GET", "/v1/health", READ),
    ("GET", "/v1/status", READ),
    ("GET", f"/v1/errors/{EXAMPLE_ERROR_CODE}", READ),
    ("GET", "/v1/wells", READ),
    ("GET", "/v1/wells/facets?state=33&by=operator", READ),
    ("GET", f"/v1/wells/status-summary?bbox={EXAMPLE_BBOX}", READ),
    ("GET", "/v1/wells/vintage-cohorts", READ),
    ("GET", f"/v1/wells/{EXAMPLE_API10}", READ),
    ("GET", f"/v1/wells/{EXAMPLE_API10}/completions", READ),
    ("GET", f"/v1/wells/{EXAMPLE_API10}/cumulatives", READ),
    ("GET", f"/v1/wells/{EXAMPLE_API10}/history", READ),
    ("GET", f"/v1/wells/{EXAMPLE_API10}/neighbors", READ),
    ("GET", f"/v1/wells/{EXAMPLE_API10}/production", READ),
    ("GET", f"/v1/wells/{EXAMPLE_API10}/production/pools", READ),
    ("GET", f"/v1/wells/{EXAMPLE_API10}/type-curve", READ),
    ("GET", f"/v1/wells/{EXAMPLE_API10}/type-curve?explain=true&explain_depth=8", READ),
    # DR-63/DR-64 add parameters, never gates: an optional flag that carried its own auth
    # answer would be a second access rule on a surface this table already covers, and it
    # would be invisible here because the table keys on the path.
    ("GET", f"/v1/wells/status-summary?bbox={EXAMPLE_BBOX}&explain=true", READ),
    ("GET", "/v1/wells/vintage-cohorts?explain=true", READ),
    ("GET", f"/v1/wells/{EXAMPLE_API10}?explain=true&explain_depth=8", READ),
    ("GET", f"/v1/wells/{EXAMPLE_API10}/completions?explain=true", READ),
    ("GET", f"/v1/wells/{EXAMPLE_API10}/cumulatives?explain=true", READ),
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
    # `read`, matched to `GET /v1/wells/{api10}/cumulatives` and decided rather than
    # inherited: this route serves a mart's published residuals as figures with handles, the
    # same class of content and the same read path. It returns no credential, no raw archive
    # byte and no account, which is what the two narrower classes are for -- `owner` is held
    # by `/v1/manifests/{id}/bytes` and the key and user routes, `session` by routes that act
    # on the caller's own session. A jurisdiction's conservation ledger is a published
    # measurement about served figures, and withholding it from a reader who may read those
    # figures would state that the number is more public than its own residual.
    ("GET", f"/v1/validators/allocation?jurisdiction={EXAMPLE_JURISDICTION}", READ),
    ("GET", f"/v1/validators/allocation?jurisdiction={EXAMPLE_JURISDICTION}&explain=true", READ),
    ("GET", "/v1/schedules", READ),
    ("GET", f"/v1/schedules/{EXAMPLE_JOB_ID}", READ),
    ("GET", "/v1/quarantine", READ),
    ("GET", "/v1/quarantine/summary", READ),
    ("GET", f"/v1/quarantine/{EXAMPLE_QUARANTINE_ID}", READ),
    ("GET", "/v1/glossary", READ),
    ("GET", "/v1/formations", READ),
    ("GET", "/v1/jurisdictions", READ),
    ("GET", "/v1/glossary/index", READ),
    ("GET", f"/v1/glossary/{EXAMPLE_TERM_ID}", READ),
    ("GET", f"/v1/tiles/{TILE['layer']}/{TILE['z']}/{TILE['x']}/{TILE['y']}.pbf", READ),
    ("GET", "/v1/keys", OWNER),
    ("POST", "/v1/keys", OWNER, ISSUE_BODY),
    ("DELETE", "/v1/keys/{key_id}", OWNER),
    ("POST", "/v1/keys/{key_id}/rotate", OWNER),
    ("GET", "/v1/session/challenge", OPEN),
    ("POST", "/v1/session", OPEN, LOGIN_BODY),
    # OPEN, deliberately. "Who am I" is not a privileged question and `nobody` is a valid
    # answer; it discloses strictly less than /v1/session/challenge, which already mints a
    # signed token for an uncredentialled caller. Gated, the ordinary first visit to a public
    # instance was a console error and a failed request on every page load.
    ("GET", "/v1/session", OPEN),
    ("DELETE", "/v1/session", SESSION),
    ("POST", "/v1/session/password", SESSION, _own_password_body),
    ("GET", "/v1/users", OWNER),
    ("POST", "/v1/users", OWNER, CREATE_USER_BODY),
    ("PATCH", "/v1/users/{user_id}", OWNER, {"role": "viewer"}),
    ("DELETE", "/v1/users/{user_id}", OWNER),
    ("POST", "/v1/users/{user_id}/password", OWNER, {"new_password": NEW_PASSWORD}),
    # OWNER, not SESSION: `_target` aims these at somebody else's session. That a viewer may
    # revoke their *own* is asserted in test_sessions_surface.py, outside the table, because
    # the table keys on the path and cannot express "the caller's own row".
    ("GET", "/v1/sessions", OWNER),
    ("DELETE", "/v1/sessions/{session_id}", OWNER),
    # Finding F-2: both were anonymous, and the coverage test below could not see it
    # because it walked document["paths"], which neither path is an entry in.
    ("GET", "/docs", READ),
    ("GET", "/openapi.json", READ),
)

CASES: tuple[Case, ...] = tuple(Case(*row) for row in MATRIX)

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
    """One client per class, each holding a credential issued through the API itself.

    Every one of them speaks https, including the key classes: the login probe has to hold the
    pre-session `__Host-` CSRF cookie, which the transport drops over http.
    """
    revoked_secret = issue_key(client, label="matrix-revoked-2026", scope="agent")
    revoked_id = next(
        row["key_id"]
        for row in client.get("/v1/keys").json()["data"]
        if row["label"] == "matrix-revoked-2026"
    )
    client.delete(f"/v1/keys/{revoked_id}")
    return {
        "anonymous": _secure(client, None),
        "invalid": _secure(client, "a-key-that-was-never-issued"),
        "revoked": _secure(client, revoked_secret),
        "guest": _secure(client, issue_key(client, label="matrix-guest-2026", scope="guest")),
        "agent": _secure(client, issue_key(client, label="matrix-agent-2026", scope="agent")),
        "owner": _secure(client, client.headers[KEY_HEADER]),
        "owner_session": owner_session,
        "viewer_session": viewer_session,
        "expired_session": expired_session,
    }


def _secure(client: TestClient, secret: str | None) -> TestClient:
    return as_principal(client, secret, base_url=SESSION_BASE_URL)


def _call(caller: TestClient, case: Case, owner: TestClient, principal: str) -> int:
    path = _target(case.path, owner)
    body = case.body(principal) if callable(case.body) else case.body
    headers = _csrf_headers(caller, case.method, path)
    return caller.request(case.method, path, json=body, headers=headers).status_code


def _target(path: str, owner: TestClient) -> str:
    """Mint whatever the templated segment names, as the owner, so the probe has a real target.

    Without one the allowed principals meet a 404 and the row would read as a refusal.
    """
    if "{key_id}" in path:
        issued = owner.post(
            "/v1/keys", json={**ISSUE_BODY, "label": f"matrix-{abs(hash(path)) % 9999}-2026"}
        )
        return path.replace("{key_id}", issued.json()["data"]["key_id"])
    if "{user_id}" in path:
        made = owner.post("/v1/users", json=PROBE_USER_BODY)
        return path.replace("{user_id}", made.json()["data"]["user_id"])
    if "{session_id}" in path:
        # Read back off the list, not minted here: `_target` holds no connection, and a login
        # would put a 250 ms floor and an Argon2id verify in front of every parametrised case.
        # The `expired-session` fixture's row is the target because no principal in the table
        # holds it live -- so a caller the matrix expects to be refused cannot be refused for
        # the wrong reason, by owning the session it was aimed at.
        listed = owner.get("/v1/sessions").json()["data"]
        target = next(row for row in listed if row["username"] == PROBE_SESSION_USERNAME)
        return path.replace("{session_id}", target["session_id"])
    return path


def _csrf_headers(caller: TestClient, method: str, path: str) -> dict[str, str]:
    """A session making a state-changing call carries a CSRF token, as a browser would.

    Without this the matrix would read every session mutation as a refusal and hide whatever
    the authorization answer actually is. Login carries one whoever is asking: it checks the
    token itself, against a pre-session nonce when the caller holds no session.
    """
    if method in SAFE_METHODS:
        return {}
    if (method, path) != LOGIN and not caller.cookies.get(SESSION_COOKIE):
        return {}
    return {CSRF_HEADER: challenge(caller)}


# A safe method writes nothing the row after it may read, so the 576 items on one share the
# worker's database inside a transaction rolled back per item instead of cloning 576 of them.
# The 99 mutating items mint keys, create users and delete sessions: they keep a database each,
# because a shared one would make the matrix order-dependent, which is worse than slow.
MATRIX_CASES = [
    pytest.param(case, marks=pytest.mark.readonly) if case.method in SAFE_METHODS else case
    for case in CASES
]


@pytest.mark.parametrize(
    "case", MATRIX_CASES, ids=lambda case: f"{case.method}-{case.path}-{case.access}"
)
@pytest.mark.parametrize("principal", PRINCIPALS)
def test_the_auth_matrix_holds(
    client: TestClient,
    principals: dict[str, TestClient],
    case: Case,
    principal: str,
) -> None:
    status = _call(principals[principal], case, client, principal)

    if _expected(case.access, principal) == "deny":
        assert status == 403, f"{principal} reached {case.method} {case.path}"
    else:
        assert status < 400, f"{principal} was refused {case.method} {case.path} with {status}"


# The gated routes that take a body, with an id that need not resolve: a caller who is refused
# never gets far enough for it to matter.
BODY_ROUTES = (
    ("POST", "/v1/users"),
    ("PATCH", "/v1/users/usr_whatever"),
    ("DELETE", "/v1/users/usr_whatever"),
    ("POST", "/v1/users/usr_whatever/password"),
    ("POST", "/v1/session/password"),
)


@pytest.mark.parametrize(("method", "path"), BODY_ROUTES, ids=lambda value: str(value))
def test_an_anonymous_caller_is_refused_before_their_body_is_read(
    principals: dict[str, TestClient], method: str, path: str
) -> None:
    """Authorization answers first, so no payload from an uncredentialled caller is examined.

    A 422 here would say the body was parsed and validated against a schema for someone who
    may not reach the route at all -- and the pointers in a validation body describe it.
    """
    response = principals["anonymous"].request(method, path, json={"not": "the schema"})

    assert response.status_code == 403, f"{method} {path} read the body before refusing"


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
    covered = {(case.method, _template(case.path.split("?")[0])) for case in CASES}

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
    covered = {(case.method, case.path.split("?")[0]) for case in CASES}
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
        (EXAMPLE_JOB_ID, "job_id"),
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
        (case.method, case.path.split("?")[0]) for case in CASES if case.access == OPEN
    }

    assert served_open == expected, "the anonymous surface changed without a ruling"
