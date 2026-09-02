"""The jurisdiction well-count ledger: what was measured, when, and by which refresh.

`lineage.jurisdiction_well_counts` is append-only and every row carries the derivation that
produced it, so a count on the wire resolves to a run and through it to the files that run
read. There is no live `count(*)` fallback anywhere: a jurisdiction with no measurement serves
no number rather than a zero, because "not measured yet" and "no wells" are different facts
(R-3).
"""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import date

import psycopg
from psycopg.rows import dict_row

from glasswell.ingest.base import resolve_environment
from glasswell.lineage import PostgresRecorder, lineage_session
from glasswell.lineage.capture import derive
from glasswell.lineage.clock import utc_today
from glasswell.lineage.jurisdictions import load_jurisdictions
from glasswell.lineage.models import InputRef, OutputSpec
from glasswell.lineage.serialization import hash_payload
from glasswell.status_resolution import resolved_status, resolver_join, resolver_rules

TOTAL_STATUS_KEY = "*total*"

# The status a well is counted under is the one the map draws it with, which for New Mexico is
# resolved at read time rather than written by the promotion — so the count reads the same view
# `/v1/wells` does, and the ledger cannot disagree with the canvas about a well's class.
# The wells the count reads, as derivation refs: without them the refresh is a graph node with
# no edge leaving it, and a served count resolves to a run that cannot be walked back to the
# regulator file. The sibling marts pass the same shape (cumulatives.py, land_metrics.py).
_INPUT_DERIVATIONS = """
select derivation_id, created_vintage
  from lineage.derivations
 where derivation_id in (select derivation_id from canonical.wells)
 order by derivation_id
"""

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


def _canonical_inputs(connection: psycopg.Connection) -> list[InputRef]:
    with connection.cursor() as cursor:
        cursor.execute(_INPUT_DERIVATIONS)
        return [
            InputRef(kind="derivation", ref_id=derivation_id, as_of_vintage=vintage)
            for derivation_id, vintage in cursor.fetchall()
        ]


def refresh_jurisdiction_counts(
    connection: psycopg.Connection,
    *,
    measured_on: date | None = None,
    codes: Collection[str] | None = None,
) -> CountRefresh:
    """Append one measurement per registered jurisdiction, by status and in total.

    Idempotent within a day by refusal rather than by overwrite: the ledger is append-only and
    its key is (jurisdiction, measured_on, status), so a second run on the same day conflicts
    and is skipped. A corrected count is a measurement on a later day, never an edit.

    `codes` narrows the refresh to some of the registered jurisdictions; the default is all of
    them. Narrowing is a partial measurement, not a smaller claim: the jurisdictions left out
    keep whatever the ledger already held, which for one never measured is no row and therefore
    no number served (R-3). It exists for a re-measure after one jurisdiction's backfill.
    """
    registry = load_jurisdictions(connection)
    registered = [
        row
        for row in registry
        if row.identity_prefix is not None
        and (codes is None or row.jurisdiction_code in codes)
    ]
    prefixes = [row.identity_prefix for row in registered]
    owner = {row.identity_prefix: row.jurisdiction_code for row in registered}
    measured = measured_on or utc_today()

    read_time = resolver_rules(connection)
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
            # Which jurisdictions were counted under a read-time class, and under which rule.
            # A count whose class came from a join has to name the rule that made the join.
            "read_time_resolution": read_time,
            "total_policy": "sum_of_measured_classes",
        },
        inputs=_canonical_inputs(connection),
        # The rules that decided the class every count is grouped by: each jurisdiction's
        # registered status vocabulary, plus the read-time resolvers, whose join inside _COUNTS
        # is what gives New Mexico a class at all. R8: a rule is referenced by the derivations
        # it shaped, and these shaped every row here.
        rules=sorted(
            {rule for row in registered if (rule := row.rule("status_vocabulary")) is not None}
            | set(read_time.values())
        ),
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


DSN_ENV = "GLASSWELL_DSN"
FALLBACK_DSN_ENV = "DATABASE_URL"


def resolved_dsn(explicit: str | None) -> str:
    """A DSN on argv is visible in /proc and lands in shell history, so the flag is optional."""
    dsn = explicit or os.environ.get(DSN_ENV) or os.environ.get(FALLBACK_DSN_ENV)
    if not dsn:
        raise SystemExit(
            f"no database DSN: pass --dsn, or set {DSN_ENV} or {FALLBACK_DSN_ENV}"
        )
    return dsn


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Measure the jurisdiction well-count ledger and append today's counts."
    )
    parser.add_argument("--dsn", default=None)
    parser.add_argument(
        "--codes",
        default=None,
        help="comma-separated jurisdiction codes; the default measures every registered one",
    )
    parser.add_argument("--env-id", default=None, help="override the fingerprinted env id")
    parser.add_argument("--code-version", default=None)
    arguments = parser.parse_args(argv)
    codes = (
        tuple(code.strip() for code in arguments.codes.split(",") if code.strip())
        if arguments.codes
        else None
    )

    with psycopg.connect(resolved_dsn(arguments.dsn)) as connection:
        environment = resolve_environment(
            connection, env_id=arguments.env_id, code_version=arguments.code_version
        )
        with lineage_session(recorder=PostgresRecorder(connection), environment=environment):
            refresh = refresh_jurisdiction_counts(connection, codes=codes)
        connection.commit()
        print(json.dumps(refresh.as_dict(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
