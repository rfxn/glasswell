"""Re-promote every staged ND month under the S-E key, without re-reading a single byte.

The widened key changes what canonical *can* represent, not what the regulator filed, so the
re-promotion reads `staging.nd_mpr_oil` — the rows the parse stage already recorded against a
verified manifest — and runs the validate, conform and promote stages over them again. It
appends a vintage; it never rewrites one (DIR-2), so a well whose value is unchanged appends
nothing and a multi-pool well gains its pool rows and their disclosed sum.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date

import psycopg
from psycopg.rows import dict_row

from glasswell.db.dsn import add_dsn_argument, resolve_dsn
from glasswell.ingest.base import IngestRun, open_ingest_run, record_vintage_day
from glasswell.ingest.nd_mpr import SOURCE_ID, STAGING_TABLE, promote_manifest
from glasswell.lineage.audit import emit
from glasswell.lineage.errors import VintageAlreadyPromoted


@dataclass(frozen=True, slots=True)
class StagedManifest:
    manifest_id: str
    source_key: str
    fetch_vintage: date


@dataclass(frozen=True, slots=True)
class RepromotionReport:
    report_vintage: date
    manifest_ids: list[str] = field(default_factory=list)
    rows_examined: int = 0
    rows_appended: int = 0
    rows_aggregated: int = 0
    collisions_superseded: int = 0
    months_touched: list[str] = field(default_factory=list)
    restatement_summary: dict[str, int] = field(default_factory=dict)
    quarantined: dict[str, int] = field(default_factory=dict)


_STAGED_MANIFESTS = f"""
select m.manifest_id, m.source_key, m.fetch_vintage
  from lineage.manifests m
 where m.source_id = %(source_id)s
   and exists (select 1 from {STAGING_TABLE} s where s.manifest_id = m.manifest_id)
 order by m.source_key, m.manifest_id
"""


def staged_manifests(
    connection: psycopg.Connection, *, source_keys: Sequence[str] | None = None
) -> list[StagedManifest]:
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(_STAGED_MANIFESTS, {"source_id": SOURCE_ID})
        manifests = [StagedManifest(**row) for row in cursor.fetchall()]
    if source_keys is None:
        return manifests
    wanted = set(source_keys)
    return [manifest for manifest in manifests if manifest.source_key in wanted]


def _refuse_duplicate_months(manifests: Sequence[StagedManifest]) -> None:
    """Two staged manifests for one workbook are two answers for one month at one vintage.

    Only reachable after a `--restage` that left the superseded manifest's rows behind. It is
    the operator's call which one is the month, so it is refused here rather than resolved by
    insertion order half-way through the run.
    """
    seen: dict[str, str] = {}
    collisions = []
    for manifest in manifests:
        first = seen.setdefault(manifest.source_key, manifest.manifest_id)
        if first != manifest.manifest_id:
            collisions.append(f"{manifest.source_key}: {first} and {manifest.manifest_id}")
    if collisions:
        raise VintageAlreadyPromoted(
            STAGING_TABLE, "this run", len(collisions), collisions[0]
        )


def repromote(
    run: IngestRun, *, source_keys: Sequence[str] | None = None
) -> RepromotionReport:
    """Re-promote every staged manifest at the run's vintage, in source-key order."""
    manifests = staged_manifests(run.connection, source_keys=source_keys)
    _refuse_duplicate_months(manifests)
    examined = appended = aggregated = superseded = 0
    months: set[str] = set()
    restatement: dict[str, int] = {}
    quarantined: dict[str, int] = {}
    promotions: list[str] = []
    for manifest in manifests:
        outcome = promote_manifest(
            run,
            manifest=manifest,
            source_key=manifest.source_key,
            partition={
                "source_key": manifest.source_key,
                "manifest_id": manifest.manifest_id,
                "repromotion": "s_e_entity_key",
            },
        )
        promotions.append(outcome.promote_derivation_id)
        examined += outcome.rows_examined
        appended += outcome.rows_appended
        aggregated += outcome.rows_aggregated
        superseded += outcome.collisions_superseded
        months.update(outcome.months_touched)
        for month, count in outcome.restatement_summary.items():
            restatement[month] = restatement.get(month, 0) + count
        for reason, count in outcome.quarantined.items():
            quarantined[reason] = quarantined.get(reason, 0) + count

    manifest_ids = [manifest.manifest_id for manifest in manifests]
    # The ledger row is the vintage-day's, so a second same-day repromotion accumulates onto
    # the first pass instead of overwriting it, and a no-op run leaves it alone (DR-78).
    if manifests and record_vintage_day(
        run.connection,
        source_id=SOURCE_ID,
        vintage_date=run.as_of,
        manifest_ids=manifest_ids,
        opened_at=run.session.clock.now(),
        # The last promotion, which is where the backfill path's per-month upsert also lands.
        promotion_derivation_id=promotions[-1] if promotions else None,
        rows_examined=examined,
        rows_appended=appended,
        months_touched=sorted(months),
        restatement_summary=restatement,
    ):
        emit(
            run.connection,
            "canonical.vintage_opened",
            subject_type="vintage",
            subject_id=f"vin_{SOURCE_ID}_{run.as_of.isoformat()}",
            payload={
                "reason": "s_e_entity_key_repromotion",
                "manifests": len(manifests),
                "rows_examined": examined,
                "rows_appended": appended,
                "rows_aggregated": aggregated,
                "collisions_superseded": superseded,
                "months_touched": sorted(months),
            },
            correlation_id=run.session.correlation_id,
            occurred_at=run.session.clock.now(),
        )
    return RepromotionReport(
        report_vintage=run.as_of,
        manifest_ids=manifest_ids,
        rows_examined=examined,
        rows_appended=appended,
        rows_aggregated=aggregated,
        collisions_superseded=superseded,
        months_touched=sorted(months),
        restatement_summary=restatement,
        quarantined=quarantined,
    )




def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Re-promote staged ND production under the S-E entity key."
    )
    add_dsn_argument(parser)
    parser.add_argument(
        "--source-key",
        action="append",
        help="Limit to one staged workbook, e.g. 2026_01.xlsx; repeatable.",
    )
    arguments = parser.parse_args(argv)
    arguments.dsn = resolve_dsn(arguments.dsn)

    with psycopg.connect(arguments.dsn) as connection:
        try:
            with open_ingest_run(connection, source_id=SOURCE_ID) as run:
                report = repromote(run, source_keys=arguments.source_key)
        except VintageAlreadyPromoted as refused:
            connection.rollback()
            print(f"refused: {refused}")
            return 2
        connection.commit()
    print(
        f"vintage {report.report_vintage}: {len(report.manifest_ids)} manifests,"
        f" examined {report.rows_examined}, appended {report.rows_appended}"
        f" (aggregates {report.rows_aggregated}),"
        f" collisions superseded {report.collisions_superseded}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
