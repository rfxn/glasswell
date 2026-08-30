"""Database-backed fixed windows for API operations that create durable evidence.

Two unmet items are recorded here rather than asserted by a test that would pass without
measuring anything. §3.6.8's "32 global concurrency" and "5 concurrent jobs" cannot be
expressed by this primitive: a fixed window counts requests per window, not simultaneous
in-flight work. Closing them needs a different mechanism, not a different constant.
"""

from __future__ import annotations

import math

import psycopg
from starlette.requests import Request

from glasswell.api.client_ip import resolve_client_ip
from glasswell.api.errors import ProblemError
from glasswell.api.principal import Principal

_CONSUME = """
insert into lineage.api_rate_windows
    (principal_id, operation, window_started_at, requests)
values (%(principal_id)s, %(operation)s, date_trunc('minute', clock_timestamp()), 1)
on conflict (principal_id, operation) do update
   set window_started_at = excluded.window_started_at,
       requests = case
           when lineage.api_rate_windows.window_started_at = excluded.window_started_at
           then lineage.api_rate_windows.requests + 1
           else 1
       end
 where lineage.api_rate_windows.window_started_at < excluded.window_started_at
    or (lineage.api_rate_windows.window_started_at = excluded.window_started_at
        and lineage.api_rate_windows.requests < %(limit)s)
returning requests
"""


def consume_rate_limit(
    connection: psycopg.Connection,
    principal: Principal,
    *,
    operation: str,
    limit: int,
) -> int:
    """Persist one request before expensive work, or refuse an exhausted fixed window."""
    if limit < 1:
        raise ValueError("rate limit must be positive")
    with connection.cursor() as cursor:
        cursor.execute(
            _CONSUME,
            {"principal_id": principal.id, "operation": operation, "limit": limit},
        )
        row = cursor.fetchone()
    if row is None:
        connection.rollback()
        raise ProblemError(
            "rate_limited",
            detail=f"{operation} permits {limit} requests per principal per UTC minute",
        )
    connection.commit()
    return int(row[0])


# The four ruled buckets, as data so a test can read the policy rather than restate it.
TILE_PREFIX = "/v1/tiles/"
BUCKETS: dict[str, int] = {
    "interactive": 120,
    "service": 60,
    "tiles": 600,
    "anonymous": 30,
}
# Rounded up to this, so the remaining-time value cannot be used to tell which bucket fired.
RETRY_AFTER_GRANULARITY = 30
WINDOW_SECONDS = 60


def bucket_for(principal: Principal, path: str) -> tuple[str, str]:
    """(bucket name, counter key). The anonymous key is the resolved address, never nothing."""
    if path.startswith(TILE_PREFIX):
        return "tiles", principal.id
    if principal.kind == "user":
        return "interactive", principal.id
    if principal.kind == "anonymous":
        return "anonymous", principal.id
    return "service", principal.id


def consume_bucket(connection: psycopg.Connection, principal: Principal, request: Request) -> str:
    """Charge one request to the bucket this caller falls in, or refuse uniformly."""
    name, key = bucket_for(principal, request.url.path)
    if name == "anonymous":
        # No principal to key on, so the resolved address is the bucket -- and an address
        # that cannot be resolved shares one bucket with every other unresolvable caller
        # rather than escaping the limit.
        key = f"ip:{resolve_client_ip(request)}"
    try:
        consume_rate_limit(connection, _keyed(principal, key), operation=name, limit=BUCKETS[name])
    except ProblemError as refused:
        if refused.code != "rate_limited":
            raise
        raise _uniform_refusal() from refused
    return name


def _keyed(principal: Principal, key: str) -> Principal:
    return principal if key == principal.id else principal.model_copy(update={"id": key})


def _uniform_refusal() -> ProblemError:
    """One body and one Retry-After for every bucket.

    Naming the bucket, or reporting the exact seconds remaining, would let a caller tell the
    per-account limiter from the per-IP one -- which is an oracle for whether an account
    exists on the login path.
    """
    retry = int(math.ceil(WINDOW_SECONDS / RETRY_AFTER_GRANULARITY) * RETRY_AFTER_GRANULARITY)
    return ProblemError(
        "rate_limited",
        detail="too many requests; retry after the interval in Retry-After",
        headers={"Retry-After": str(retry)},
    )
