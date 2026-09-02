"""The jurisdiction well-count ledger: what was measured, when, and by which refresh.

`lineage.jurisdiction_well_counts` is append-only and every row carries the derivation that
produced it, so a count on the wire resolves to a run and through it to the files that run
read. There is no live `count(*)` fallback anywhere: a jurisdiction with no measurement serves
no number rather than a zero, because "not measured yet" and "no wells" are different facts
(R-3).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import psycopg
from psycopg.rows import dict_row

from glasswell.lineage.capture import derive
from glasswell.lineage.clock import utc_today
from glasswell.lineage.jurisdictions import load_jurisdictions
from glasswell.lineage.models import OutputSpec
from glasswell.lineage.serialization import hash_payload
from glasswell.status_resolution import resolved_status, resolver_join

TOTAL_STATUS_KEY = "*total*"

# The status a well is counted under is the one the map draws it with, which for New Mexico is
# resolved at read time rather than written by the promotion — so the count reads the same view
# `/v1/wells` does, and the ledger cannot disagree with the canvas about a well's class.
_COUNTS = f"""
select w.state_code, {resolved_status("w")} as status_canonical, count(*)::int as well_count
  from canonical.wells_latest w
  {resolver_join("w")}
 where w.state_code = any(%(prefixes)s)
 group by w.state_code, {resolved_status("w")}
"""


@dataclass(frozen=True, slots=True)
class CountRefresh:
    derivation_id: str
    measured_on: date
    rows: int

    def as_dict(self) -> dict[str, object]:
        return {
            "derivation_id": self.derivation_id,
            "measured_on": self.measured_on.isoformat(),
            "rows": self.rows,
        }


def refresh_jurisdiction_counts(
    connection: psycopg.Connection, *, measured_on: date | None = None
) -> CountRefresh:
    """Append one measurement per registered jurisdiction, by status and in total.

    Idempotent within a day by refusal rather than by overwrite: the ledger is append-only and
    its key is (jurisdiction, measured_on, status), so a second run on the same day conflicts
    and is skipped. A corrected count is a measurement on a later day, never an edit.
    """
    registry = load_jurisdictions(connection)
    registered = [row for row in registry if row.identity_prefix is not None]
    prefixes = [row.identity_prefix for row in registered]
    owner = {row.identity_prefix: row.jurisdiction_code for row in registered}
    measured = measured_on or utc_today()

    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(_COUNTS, {"prefixes": prefixes})
        counted = [dict(row) for row in cursor.fetchall()]

    appended: list[dict[str, object]] = []
    for row in registered:
        classes = [item for item in counted if item["state_code"] == row.identity_prefix]
        # The total is the sum of the classes rather than a second `count(*)`: two queries are
        # two chances for the parts not to add up to the whole a reader is shown beside them.
        appended.append(
            {
                "jurisdiction_code": row.jurisdiction_code,
                "status_canonical": None,
                "well_count": sum(int(item["well_count"]) for item in classes),
            }
        )
        appended += [
            {
                "jurisdiction_code": row.jurisdiction_code,
                "status_canonical": item["status_canonical"],
                "well_count": int(item["well_count"]),
            }
            for item in classes
            if item["status_canonical"] is not None
        ]

    with derive(
        "mart.refresh",
        output=OutputSpec(
            store="postgres",
            dataset="lineage.jurisdiction_well_counts",
            partition={"measured_on": measured.isoformat()},
            schema_version="1",
        ),
        params={
            "jurisdictions": sorted(owner.values()),
            "status_source": "canonical.status_resolution_else_promoted_class",
            "total_policy": "sum_of_measured_classes",
        },
        inputs=[],
    ) as context:
        context.set_rows(len(appended))
        context.set_output_hash(
            hash_payload(
                {
                    "measured_on": measured.isoformat(),
                    "counts": sorted(
                        (
                            str(row["jurisdiction_code"]),
                            str(row["status_canonical"] or TOTAL_STATUS_KEY),
                            int(row["well_count"]),  # type: ignore[arg-type]
                        )
                        for row in appended
                    ),
                }
            )
        )
    derivation_id = context.derivation_id

    with connection.cursor() as cursor:
        cursor.executemany(
            "insert into lineage.jurisdiction_well_counts"
            " (jurisdiction_code, measured_on, status_canonical, well_count, derivation_id)"
            " values (%(jurisdiction_code)s, %(measured_on)s, %(status_canonical)s,"
            "         %(well_count)s, %(derivation_id)s)"
            " on conflict do nothing",
            [
                {**row, "measured_on": measured, "derivation_id": derivation_id}
                for row in appended
            ],
        )
    return CountRefresh(derivation_id=derivation_id, measured_on=measured, rows=len(appended))
