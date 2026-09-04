"""The durable poll and registered-artifact freshness view, below the API.

`status/models.py` computes the freshness verdict; this module holds the query that feeds it.
It lived in `api/routers/health.py`, which put the scheduler in the position of importing a
FastAPI router to find out what is due. It is typed on `psycopg.Connection` and imports nothing
from `glasswell.api`, so the router, the collector and the planner all read one rule.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime
from typing import Any

import psycopg
from psycopg.rows import dict_row

from glasswell.status.models import source_freshness

_SOURCES = """
select s.source_id,
       s.name,
       artifact.fetch_vintage as retrieval_vintage,
       -- The parse's half of freshness. A fetch and a parse are two outcomes: an ingest that
       -- keeps its manifest when the parse refuses leaves an honestly successful poll behind,
       -- so the poll alone cannot say whether the artifact was ever read. Two arms, because
       -- the recorded refusal is precise and the unstamped column is the backstop for a run
       -- that died before it could record one. staging_load_ref is 003_manifests.sql:24.
       coalesce(artifact.manifest_id is not null and (
            exists (select 1 from lineage.audit_events e
                     where e.event_type = 'staging.load_failed'
                       and e.subject_type = 'manifest'
                       and e.subject_id = artifact.manifest_id)
         or (artifact.staging_load_ref is null
             and exists (select 1 from lineage.manifests loaded
                          where loaded.source_id = s.source_id
                            and loaded.staging_load_ref is not null))
       ), false) as artifact_unloaded,
       coalesce(artifact_count.manifest_count, 0) as manifest_count,
       artifact.manifest_id as last_manifest_id,
       artifact.fetched_at as last_manifest_fetched_at,
       (select max(v.vintage_date) from lineage.vintages v
         where v.source_id = s.source_id) as declared_vintage,
       p.cadence,
       p.expected_poll_interval,
       p.attempt_timeout,
       a.attempted_at as last_attempt_at,
       a.completed_at as last_attempt_completed_at,
       a.outcome as last_recorded_outcome,
       a.failure_code as last_failure_code,
       a.failure_detail as last_failure_detail,
       coalesce(k.failed_keys, 0) as unresolved_failed_keys,
       coalesce(k.open_keys, 0) as unresolved_open_keys,
       k.oldest_open_attempt_at,
       k.blocking_failure_code,
       k.blocking_failure_detail
  from lineage.sources s
  left join lineage.source_poll_policies p on p.source_id = s.source_id
  left join lateral (
       select observed.manifest_id, observed.fetched_at, observed.fetch_vintage,
              observed.staging_load_ref
         from (
              select m.manifest_id, m.fetched_at, m.fetch_vintage, m.staging_load_ref,
                     m.fetched_at as observed_at, 0 as observation_rank
                from lineage.manifests m
               where m.source_id = s.source_id
              union all
              select m.manifest_id, m.fetched_at, m.fetch_vintage, m.staging_load_ref,
                     f.completed_at as observed_at, 1 as observation_rank
                from lineage.fetch_attempts f
                join lineage.manifests m on m.manifest_id = f.manifest_id
               where f.source_id = s.source_id
                 and f.outcome in ('new', 'unchanged')
         ) observed
        order by observed.observed_at desc, observed.observation_rank desc,
                 observed.manifest_id desc
        limit 1
  ) artifact on true
  left join lateral (
       select count(distinct m.manifest_id) as manifest_count
         from lineage.manifests m
        where m.source_id = s.source_id
           or exists (
              select 1 from lineage.fetch_attempts f
               where f.source_id = s.source_id
                 and f.manifest_id = m.manifest_id
                 and f.outcome in ('new', 'unchanged')
           )
  ) artifact_count on true
  left join lateral (
       select f.attempted_at, f.completed_at, f.outcome, f.failure_code, f.failure_detail
         from lineage.fetch_attempts f
        where f.source_id = s.source_id
        order by f.attempted_at desc, f.attempt_id desc
        limit 1
  ) a on true
  left join lateral (
       select count(*) filter (where latest.outcome = 'failed') as failed_keys,
              count(*) filter (where latest.outcome is null) as open_keys,
              min(latest.attempted_at) filter (where latest.outcome is null)
                  as oldest_open_attempt_at,
              (array_agg(latest.failure_code order by latest.attempted_at desc,
                         latest.attempt_id desc)
                  filter (where latest.outcome = 'failed'))[1] as blocking_failure_code,
              (array_agg(latest.failure_detail order by latest.attempted_at desc,
                         latest.attempt_id desc)
                  filter (where latest.outcome = 'failed'))[1] as blocking_failure_detail
         from (
              select distinct on (f.source_key)
                     f.source_key, f.attempt_id, f.attempted_at, f.outcome,
                     f.failure_code, f.failure_detail
                from lineage.fetch_attempts f
               where f.source_id = s.source_id
               order by f.source_key, f.attempted_at desc, f.attempt_id desc
         ) latest
  ) k on true
 where (%(source_ids)s::text[] is null or s.source_id = any(%(source_ids)s))
 order by s.source_id
"""


def _iso(value: datetime | date | None) -> str | None:
    return value.isoformat() if value is not None else None


def source_health_data(
    connection: psycopg.Connection,
    *,
    observed_at: datetime,
    source_ids: Sequence[str] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """The shared durable poll and registered-artifact freshness view."""
    served: list[dict[str, Any]] = []
    freshness: dict[str, Any] = {}
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            _SOURCES,
            {"source_ids": list(source_ids) if source_ids is not None else None},
        )
        rows = cursor.fetchall()
    for row in rows:
        assessed = source_freshness(
            observed_at=observed_at,
            artifact_at=row["last_manifest_fetched_at"],
            attempted_at=row["last_attempt_at"],
            completed_at=row["last_attempt_completed_at"],
            recorded_outcome=row["last_recorded_outcome"],
            expected_interval=row["expected_poll_interval"],
            attempt_timeout=row["attempt_timeout"],
            cadence=row["cadence"],
            failure_code=row["last_failure_code"],
            failure_detail=row["last_failure_detail"],
            unresolved_failed_keys=row["unresolved_failed_keys"],
            unresolved_open_keys=row["unresolved_open_keys"],
            oldest_open_attempt_at=row["oldest_open_attempt_at"],
            blocking_failure_code=row["blocking_failure_code"],
            blocking_failure_detail=row["blocking_failure_detail"],
            artifact_unloaded=row["artifact_unloaded"],
        )
        source = {
            "source_id": row["source_id"],
            "name": row["name"],
            "state": assessed.state,
            "retrieval_vintage": _iso(row["retrieval_vintage"]),
            "declared_vintage": _iso(row["declared_vintage"]),
            "last_manifest_id": row["last_manifest_id"],
            "manifest_count": row["manifest_count"],
            "last_attempt_at": _iso(row["last_attempt_at"]),
            "last_outcome": assessed.last_outcome,
            "next_expected_poll": _iso(assessed.next_expected_poll),
            "cadence": row["cadence"],
            "freshness_reason": assessed.reason,
        }
        served.append(source)
        freshness[row["source_id"]] = {
            "retrieval_vintage": _iso(row["retrieval_vintage"]),
            "declared_vintage": _iso(row["declared_vintage"]),
            "state": assessed.state,
            "last_attempt_at": _iso(row["last_attempt_at"]),
            "last_outcome": assessed.last_outcome,
            "next_expected_poll": _iso(assessed.next_expected_poll),
            "cadence": row["cadence"],
            "reason": assessed.reason,
        }
    return served, freshness
