"""Who is calling, and what that buys them (SB-06 §8.3, DIR-6, reconciliation S-G).

Three scopes, one credential mechanism. `owner` is the deployment's operator, `agent` is a
non-interactive integration, `guest` is the stranger S1 hands a key to. S-G's ruling is the
reason the scope lives on the key rather than on the Access class: a service principal has
to be able to *be* a guest, which an access class cannot express.

Fail-closed is the whole design. An unknown key, a revoked key, an expired key, an
unreachable key store and an empty key table all produce the same answer, because a caller
who can tell them apart has an oracle.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import Literal, Protocol

import psycopg
from psycopg.rows import dict_row

from glasswell.api.errors import ProblemError
from glasswell.lineage.models import Frozen

Scope = Literal["owner", "agent", "guest"]
SCOPES: tuple[Scope, ...] = ("owner", "agent", "guest")

# S-G splits POSTs by effect, not by verb. Compute POSTs are pure and content-addressed, so
# a guest may run them; mutation POSTs change durable state and stay with the owner. The
# agent-with-write half of S-G's mutation rule needs a capability on the key and is not built.
COMPUTE_POST_SCOPES: tuple[Scope, ...] = ("owner", "agent", "guest")
MUTATION_POST_SCOPES: tuple[Scope, ...] = ("owner",)

SECRET_BYTES = 32
KEY_ID_PREFIX = "key_"


class KeyRecord(Frozen):
    key_id: str
    label: str
    scope: Scope
    created_at: datetime
    created_by: str
    expires_at: datetime | None = None
    revoked_at: datetime | None = None
    revoked_by: str | None = None
    last_used_at: datetime | None = None

    def state(self, *, now: datetime) -> str:
        if self.revoked_at is not None:
            return "revoked"
        if self.expires_at is not None and self.expires_at <= now:
            return "expired"
        return "active"


Role = Literal["owner", "viewer"]

# `role` is the user-facing concept; `scope` stays the internal authorization key, so every
# existing guard, matrix row and redaction site keeps reading the field it already reads.
_ROLE_FOR_SCOPE: dict[Scope, Role] = {"owner": "owner", "agent": "viewer", "guest": "viewer"}
_SCOPE_FOR_ROLE: dict[Role, Scope] = {"owner": "owner", "viewer": "guest"}


def role_for_scope(scope: Scope) -> Role:
    return _ROLE_FOR_SCOPE[scope]


def scope_for_role(role: Role) -> Scope:
    return _SCOPE_FOR_ROLE[role]


class Principal(Frozen):
    """The resolved caller. `id` is what a rate limiter and the audit stream key on."""

    id: str
    kind: Literal["owner", "service", "anonymous", "user"]
    scope: Scope
    role: Role = "viewer"
    key_id: str | None = None
    user_id: str | None = None
    session_id: str | None = None
    label: str | None = None


def fingerprint(cleartext: str) -> str:
    return hashlib.sha256(cleartext.encode("utf-8")).hexdigest()


def mint_secret() -> str:
    return secrets.token_urlsafe(SECRET_BYTES)


class KeyStore(Protocol):
    def authenticate(self, sha256: str) -> KeyRecord | None: ...


_SELECT_COLUMNS = (
    "key_id, label, scope, created_at, created_by, expires_at, revoked_at, revoked_by,"
    " last_used_at"
)

# One statement: the lookup is also the use record, so a revoked key that is still in
# circulation leaves a trace of the attempt rather than resolving silently to nothing.
_AUTHENTICATE = f"""
update lineage.api_keys
   set last_used_at = now()
 where sha256 = %(sha256)s
returning {_SELECT_COLUMNS}
"""


def _record(row: dict) -> KeyRecord:
    return KeyRecord(**row)


class PostgresKeyStore:
    """Reads through a connection it owns: auth runs on routes that never touch the pool."""

    def __init__(self, connect: Callable[[], psycopg.Connection]) -> None:
        self._connect = connect

    def authenticate(self, sha256: str) -> KeyRecord | None:
        connection = self._connect()
        try:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(_AUTHENTICATE, {"sha256": sha256})
                row = cursor.fetchone()
            connection.commit()
            return _record(dict(row)) if row else None
        finally:
            connection.close()


class ConnectionKeyStore:
    """A store bound to one live connection — the shape a request handler and a test share."""

    def __init__(self, connection: psycopg.Connection) -> None:
        self._connection = connection

    def authenticate(self, sha256: str) -> KeyRecord | None:
        with self._connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(_AUTHENTICATE, {"sha256": sha256})
            row = cursor.fetchone()
            return _record(dict(row)) if row else None


class DeniedKeyStore:
    """No store configured. Denying is the answer; defaulting open is the failure mode."""

    def authenticate(self, sha256: str) -> KeyRecord | None:
        return None


def resolve_principal(
    presented: str | None, *, owner_key: str, store: KeyStore, now: datetime
) -> Principal:
    """The single place a credential becomes a principal."""
    if not presented:
        raise ProblemError("key_required", detail="send the key in X-Glasswell-Key")
    if owner_key and hmac.compare_digest(presented, owner_key):
        return Principal(id="owner", kind="owner", scope="owner", role="owner")
    record = store.authenticate(fingerprint(presented))
    if record is None:
        raise ProblemError("unauthenticated")
    state = record.state(now=now)
    if state != "active":
        raise ProblemError("key_revoked", detail=f"the key is {state}")
    return Principal(
        id=f"key:{record.key_id}",
        kind="service",
        scope=record.scope,
        role=role_for_scope(record.scope),
        key_id=record.key_id,
        label=record.label,
    )


def check_scope(principal: Principal, allowed: Sequence[Scope]) -> Principal:
    if principal.scope not in allowed:
        raise ProblemError("forbidden", detail=f"this operation is {' or '.join(allowed)} scope")
    # GLASSWELL_ALLOW_ANON resolves to owner scope with no credential presented, so a mutation
    # reached that way mints durable state that outlives the flag. It stays a read break-glass.
    if principal.kind == "anonymous" and tuple(allowed) == MUTATION_POST_SCOPES:
        raise ProblemError("forbidden", detail="this operation needs a credential, not a flag")
    return principal


DSN_ENV = "GLASSWELL_DSN"
FALLBACK_DSN_ENV = "DATABASE_URL"


def key_store_from_environment() -> KeyStore:
    dsn = os.environ.get(DSN_ENV) or os.environ.get(FALLBACK_DSN_ENV)
    if not dsn:
        return DeniedKeyStore()
    return PostgresKeyStore(lambda: psycopg.connect(dsn))


def utc_now() -> datetime:
    return datetime.now(UTC)
