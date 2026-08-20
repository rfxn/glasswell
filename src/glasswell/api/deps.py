"""Dependencies and the environment contract: connection, owner key, as-of, paging."""

from __future__ import annotations

import hmac
import os
from collections.abc import Iterator
from datetime import UTC, date, datetime
from typing import Annotated

import psycopg
from fastapi import Depends, Query, Security
from fastapi.security import APIKeyHeader
from psycopg.rows import dict_row

from glasswell.api.errors import ProblemError
from glasswell.api.examples import KEY_HEADER
from glasswell.api.pagination import DEFAULT_LIMIT, SPINE_LIMIT_CAP, WELLS_LIMIT_CAP

OWNER_KEY_ENV = "GLASSWELL_OWNER_KEY"
ALLOW_ANON_ENV = "GLASSWELL_ALLOW_ANON"
DSN_ENV = "GLASSWELL_DSN"
FALLBACK_DSN_ENV = "DATABASE_URL"
MARTIN_URL_ENV = "GLASSWELL_MARTIN_URL"
WEB_ROOT_ENV = "GLASSWELL_WEB_ROOT"
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


def require_key(presented: Annotated[str | None, Security(owner_key_scheme)] = None) -> str:
    """A single static owner key. Rev 2 (C12) honours no origin header: it is client-settable."""
    if os.environ.get(ALLOW_ANON_ENV) == "1":
        return "anonymous"
    if not presented:
        raise ProblemError("key_required", detail=f"send the owner key in {KEY_HEADER}")
    expected = os.environ.get(OWNER_KEY_ENV, "")
    if not expected or not hmac.compare_digest(presented, expected):
        raise ProblemError("unauthenticated")
    return "owner"


def rows(connection: psycopg.Connection, statement: str, params: object = None) -> list[dict]:
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(statement, params)  # type: ignore[arg-type]
        return [dict(row) for row in cursor.fetchall()]


def today() -> date:
    return datetime.now(UTC).date()


Connection = Annotated[psycopg.Connection, Depends(get_connection)]
Principal = Annotated[str, Depends(require_key)]

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
