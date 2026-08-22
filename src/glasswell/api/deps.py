"""Dependencies and the environment contract: connection, owner key, as-of, paging."""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from datetime import UTC, date, datetime
from typing import Annotated

import psycopg
from fastapi import Depends, Query, Security
from fastapi.security import APIKeyHeader
from psycopg.rows import dict_row
from pydantic import BaseModel, Field

from glasswell.api.errors import ProblemError
from glasswell.api.examples import KEY_HEADER
from glasswell.api.pagination import DEFAULT_LIMIT, SPINE_LIMIT_CAP, WELLS_LIMIT_CAP
from glasswell.api.principal import (
    KeyStore,
    Scope,
    check_scope,
    key_store_from_environment,
    resolve_principal,
    utc_now,
)
from glasswell.api.principal import (
    Principal as ResolvedPrincipal,
)
from glasswell.lineage.explain import DEFAULT_DEPTH, MAX_DEPTH

OWNER_KEY_ENV = "GLASSWELL_OWNER_KEY"
ALLOW_ANON_ENV = "GLASSWELL_ALLOW_ANON"
DSN_ENV = "GLASSWELL_DSN"
FALLBACK_DSN_ENV = "DATABASE_URL"
MARTIN_URL_ENV = "GLASSWELL_MARTIN_URL"
WEB_ROOT_ENV = "GLASSWELL_WEB_ROOT"
BASEMAP_ROOT_ENV = "GLASSWELL_BASEMAP_ROOT"
DEFAULT_MARTIN_URL = "http://127.0.0.1:3000"


def get_connection() -> Iterator[psycopg.Connection]:
    """One connection per request, rolled back on the way out: every route here reads."""
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


def require_key(
    presented: Annotated[str | None, Security(owner_key_scheme)] = None,
    store: Annotated[KeyStore, Depends(get_key_store)] = None,  # type: ignore[assignment]
) -> ResolvedPrincipal:
    """The static owner key, then the issued keys. Rev 2 (C12) honours no origin header."""
    if os.environ.get(ALLOW_ANON_ENV) == "1":
        return ResolvedPrincipal(id="anonymous", kind="anonymous", scope="owner")
    return resolve_principal(
        presented,
        owner_key=os.environ.get(OWNER_KEY_ENV, ""),
        store=store,
        now=utc_now(),
    )


def rows(connection: psycopg.Connection, statement: str, params: object = None) -> list[dict]:
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(statement, params)  # type: ignore[arg-type]
        return [dict(row) for row in cursor.fetchall()]


def today() -> date:
    return datetime.now(UTC).date()


Connection = Annotated[psycopg.Connection, Depends(get_connection)]
Principal = Annotated[ResolvedPrincipal, Depends(require_key)]


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
