"""Database-backed fixed windows for API operations that create durable evidence."""

from __future__ import annotations

import psycopg

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
