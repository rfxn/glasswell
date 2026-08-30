"""Dependencies and the environment contract: connection, owner key, as-of, paging."""

from __future__ import annotations

import hmac
import os
from collections.abc import Callable, Iterator
from datetime import date
from typing import Annotated

import psycopg
from fastapi import Depends, Header, Query, Request, Security
from fastapi.security import APIKeyHeader
from psycopg.rows import dict_row
from pydantic import BaseModel, Field

from glasswell.api.accounts import (
    DeniedSessionStore,
    PostgresSessionStore,
    SessionStore,
)
from glasswell.api.client_ip import edge_of
from glasswell.api.csrf import CSRF_HEADER, SAFE_METHODS
from glasswell.api.csrf import check as csrf_check
from glasswell.api.errors import ProblemError
from glasswell.api.examples import KEY_HEADER
from glasswell.api.pagination import DEFAULT_LIMIT, SPINE_LIMIT_CAP, WELLS_LIMIT_CAP
from glasswell.api.principal import (
    KeyStore,
    Scope,
    check_scope,
    key_store_from_environment,
    resolve_principal,
    scope_for_role,
    utc_now,
)
from glasswell.api.principal import (
    Principal as ResolvedPrincipal,
)
from glasswell.api.rate_limit import consume_bucket
from glasswell.lineage.clock import utc_today
from glasswell.lineage.explain import DEFAULT_DEPTH, MAX_DEPTH

OWNER_KEY_ENV = "GLASSWELL_OWNER_KEY"
ALLOW_ANON_ENV = "GLASSWELL_ALLOW_ANON"
PUBLIC_ENV = "GLASSWELL_PUBLIC"
SESSION_COOKIE = "__Host-gw_session"
DSN_ENV = "GLASSWELL_DSN"
FALLBACK_DSN_ENV = "DATABASE_URL"
MARTIN_URL_ENV = "GLASSWELL_MARTIN_URL"
WEB_ROOT_ENV = "GLASSWELL_WEB_ROOT"
BASEMAP_ROOT_ENV = "GLASSWELL_BASEMAP_ROOT"
DEFAULT_MARTIN_URL = "http://127.0.0.1:3000"


def get_connection() -> Iterator[psycopg.Connection]:
    """One connection per request; committed writes survive, while unfinished work rolls back."""
    dsn = os.environ.get(DSN_ENV) or os.environ.get(FALLBACK_DSN_ENV)
    if not dsn:
        raise ProblemError(
            "service_degraded", detail=f"no database DSN: set {DSN_ENV} or {FALLBACK_DSN_ENV}"
        )
    connection = psycopg.connect(dsn)
    try:
        yield connection
    finally:
        connection.rollback()
        connection.close()


owner_key_scheme = APIKeyHeader(
    name=KEY_HEADER,
    auto_error=False,
    description="Static owner key for this deployment. /healthz and the frontend are open.",
)


def get_key_store() -> KeyStore:
    """Resolved per request and consulted only when the static owner key does not match, so
    a route that needs no database (`/v1/errors/{code}`) still needs none to authenticate."""
    return key_store_from_environment()


def get_session_store() -> SessionStore:
    """Resolved per request and consulted only when a session cookie was presented, so a
    route that needs no database still needs none to authenticate."""
    dsn = os.environ.get(DSN_ENV) or os.environ.get(FALLBACK_DSN_ENV)
    if not dsn:
        return DeniedSessionStore()
    return PostgresSessionStore(lambda: psycopg.connect(dsn))


def require_principal(
    request: Request,
    presented: Annotated[str | None, Security(owner_key_scheme)] = None,
    store: Annotated[KeyStore, Depends(get_key_store)] = None,  # type: ignore[assignment]
    sessions: Annotated[SessionStore, Depends(get_session_store)] = None,  # type: ignore[assignment]
) -> ResolvedPrincipal:
    """Session cookie, then the static owner key, then an issued key, then the anon flag.

    The cookie is tried first and wins outright when it resolves: a browser that has logged
    in should not silently fall back to a key it also happens to be holding.
    """
    now = utc_now()
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        resolved = sessions.authenticate(token, now=now)
        if resolved is not None:
            session, user = resolved
            return ResolvedPrincipal(
                id=f"user:{user.user_id}",
                kind="user",
                scope=scope_for_role(user.role),
                role=user.role,
                user_id=user.user_id,
                session_id=session.session_id,
                label=user.username,
            )

    if os.environ.get(ALLOW_ANON_ENV) == "1":
        # Narrowed from owner scope: a flag must not reach owner-only data. The startup
        # abort in create_app() is what keeps it off a public instance entirely.
        return ResolvedPrincipal(
            id="anonymous", kind="anonymous", scope="guest", role="viewer"
        )

    owner_key = os.environ.get(OWNER_KEY_ENV, "")
    # The static owner key has no expiry, no rotation path and no revocation row. After this
    # track it is a deploy-gate credential, so it is not reachable from the internet. Issued
    # api_keys rows carry an expiry and a revocation row and are unaffected on the tunnel --
    # which is what keeps the non-interactive path alive for a caller holding one.
    if (
        owner_key
        and presented
        and edge_of(request) == "tunnel"
        and hmac.compare_digest(presented, owner_key)
    ):
        raise ProblemError("unauthenticated")

    return resolve_principal(
        presented,
        owner_key=owner_key,
        store=store,
        now=now,
    )


def optional_principal(
    request: Request,
    presented: Annotated[str | None, Security(owner_key_scheme)] = None,
    store: Annotated[KeyStore, Depends(get_key_store)] = None,  # type: ignore[assignment]
    sessions: Annotated[SessionStore, Depends(get_session_store)] = None,  # type: ignore[assignment]
) -> ResolvedPrincipal | None:
    """The same resolution, with a refusal expressed as None.

    For the two open routes, which must answer whether or not a credential was presented.
    """
    try:
        return require_principal(request, presented, store, sessions)
    except ProblemError:
        return None


CSRF_PARAMETER = Annotated[
    str | None,
    Header(
        alias=CSRF_HEADER,
        description=(
            "Token from `GET /v1/session/challenge`, bound to the calling session and signed."
            " Required on every state-changing request made with a session cookie; a caller"
            " presenting an API key does not send one, because a key is not ambient authority."
        ),
    ),
]


def csrf_binding(principal: ResolvedPrincipal | None) -> str:
    """CSRF tokens bind to the session id.

    The id is opaque, server-side and changes on every login, so a token minted before a
    rotation stops working after it. Nothing credential-derived goes into the token itself.
    """
    if principal is None or not principal.session_id:
        return ""
    return f"ses:{principal.session_id}"


def require_csrf(
    request: Request,
    principal: Annotated[ResolvedPrincipal, Depends(require_principal)],
    presented: CSRF_PARAMETER = None,
) -> None:
    """Attached to the whole /v1 router set, so a new state-changing route cannot forget it.

    Enforced for cookie-authenticated callers only. CSRF is an ambient-authority problem: a
    browser attaches the cookie to a cross-site request by itself. `X-Glasswell-Key` is never
    sent automatically, so a key-authenticated caller has nothing to forge -- and demanding a
    token there would break the deploy gate, which runs with no browser and no cookie jar.
    """
    if request.method in SAFE_METHODS or principal.kind != "user":
        return
    if not presented or not csrf_check(presented, csrf_binding(principal), now=utc_now()):
        raise ProblemError("forbidden", detail=f"send a valid {CSRF_HEADER}")


# Kept so no import site breaks; `require_principal` is the name the resolution order lives
# under now.
require_key = require_principal


def enforce_rate_limit(
    request: Request,
    connection: Annotated[psycopg.Connection, Depends(get_connection)],
    principal: Annotated[ResolvedPrincipal, Depends(require_principal)],
) -> None:
    """Charge every /v1 request to one of the four ruled buckets.

    Attached to the router set rather than per operation, so a new route is limited by
    existing, not by somebody remembering. The per-operation call in routers/wells.py stays:
    the viewport provenance write has its own tighter budget and the two stack deliberately.
    """
    consume_bucket(connection, principal, request)


def rows(connection: psycopg.Connection, statement: str, params: object = None) -> list[dict]:
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(statement, params)  # type: ignore[arg-type]
        return [dict(row) for row in cursor.fetchall()]


def today() -> date:
    return utc_today()


Connection = Annotated[psycopg.Connection, Depends(get_connection)]
Principal = Annotated[ResolvedPrincipal, Depends(require_principal)]


def require_scope(*allowed: Scope) -> Callable[[ResolvedPrincipal], ResolvedPrincipal]:
    """Guard a route by scope. The allowed set is data, so the auth matrix reads off it."""

    def guard(principal: Principal) -> ResolvedPrincipal:
        return check_scope(principal, allowed)

    return guard


class PostFlags(BaseModel):
    """S-K: `?explain=true` is allowed on POST post-hoc; only the combination is refused."""

    explain: bool = Field(description="Attach the derivation chain for what the call produced.")
    dry_run: bool = Field(description="Validate and report, without creating anything.")


def post_flags(
    explain: Annotated[
        bool, Query(description="Explain the run this call created, after it has run.")
    ] = False,
    dry_run: Annotated[
        bool, Query(description="Validate the request and report; create nothing.")
    ] = False,
) -> PostFlags:
    if explain and dry_run:
        raise ProblemError(
            "explain_on_dry_run",
            detail="a dry run produces no artifact, so there is nothing to explain",
            errors=[
                {
                    "pointer": "/query/explain",
                    "code": "explain_on_dry_run",
                    "detail": "drop one of explain or dry_run",
                }
            ],
        )
    return PostFlags(explain=explain, dry_run=dry_run)


PostEffect = Annotated[PostFlags, Depends(post_flags)]


class ExplainFlags(BaseModel):
    """SB-07 §9.2's GET row, as the two parameters that carry it."""

    explain: bool = Field(description="Inline a chain for every handle the response carries.")
    explain_depth: int = Field(description="Levels the inlined walk goes back.")


def explain_flags(
    explain: Annotated[
        bool,
        Query(
            description=(
                "Resolve every derivation handle this response carries and inline the chains"
                " under `_explain`, keyed by handle. Values are unchanged: the flag adds a"
                " block and moves nothing else, so a cached or replayed comparison is"
                " unaffected by it (SB-07 §9.2)."
            )
        ),
    ] = False,
    explain_depth: Annotated[
        int,
        Query(
            ge=1,
            le=MAX_DEPTH,
            description=(
                f"How many levels back an inlined chain walks: {DEFAULT_DEPTH} by default,"
                f" {MAX_DEPTH} at most. Over the cap is refused, never clamped. A chain that"
                " stops short says so in its own `truncated` field."
            ),
        ),
    ] = DEFAULT_DEPTH,
) -> ExplainFlags:
    return ExplainFlags(explain=explain, explain_depth=explain_depth)


ExplainEffect = Annotated[ExplainFlags, Depends(explain_flags)]

AsOf = Annotated[
    date | None,
    Query(
        description=(
            "Knowledge-time cut: serve the greatest vintage at or before this date."
            " Defaults to the latest published vintage, never to wall-clock now."
        )
    ),
]
Cursor = Annotated[
    str | None,
    Query(description="Opaque cursor from meta.next_cursor. There is no offset parameter."),
]
WellsLimit = Annotated[
    int,
    Query(
        ge=1,
        le=WELLS_LIMIT_CAP,
        description=f"Page size, {DEFAULT_LIMIT} by default, {WELLS_LIMIT_CAP} at most.",
    ),
]
SpineLimit = Annotated[
    int,
    Query(
        ge=1,
        le=SPINE_LIMIT_CAP,
        description=(
            f"Page size, {DEFAULT_LIMIT} by default, {SPINE_LIMIT_CAP} at most"
            " (SB-07 §9.5 caps the spine collections lower than the data ones)."
        ),
    ),
]
