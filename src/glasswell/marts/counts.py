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
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import date

import psycopg
from psycopg.rows import dict_row

from glasswell.ingest.base import resolve_environment
from glasswell.lineage.capture import derive, lineage_session
from glasswell.lineage.clock import utc_today
from glasswell.lineage.jurisdictions import load_jurisdictions
from glasswell.lineage.models import InputRef, OutputSpec
from glasswell.lineage.serialization import hash_payload
from glasswell.lineage.store import PostgresRecorder
from glasswell.status_resolution import (
    UNMAPPED_CLASS,
    resolved_status,
    resolver_join,
    resolver_rules,
    served_status_vocabulary,
)

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
    # The registered vocabulary, crossed with every jurisdiction below. `group by` yields no
    # group for a class nothing carries, so without this a class with no wells is absent from
    # the ledger and indistinguishable from one nobody has counted -- and the client cannot
    # tell "none here" from "not measured" if the writer does not say which.
    vocabulary = [*served_status_vocabulary(connection), UNMAPPED_CLASS]
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(_COUNTS, {"prefixes": prefixes})
        counted = [dict(row) for row in cursor.fetchall()]

    appended: list[dict[str, object]] = []
    for row in registered:
        # The null bucket is the absence class the canvas already paints and the legend already
        # keys on, not a gap between the total and the rows served beside it.
        classes = {
            str(item["status_canonical"] or UNMAPPED_CLASS): int(item["well_count"])
            for item in counted
            if item["state_code"] == row.identity_prefix
        }
        # The total is the sum of the classes rather than a second `count(*)`: two queries are
        # two chances for the parts not to add up to the whole a reader is shown beside them.
        appended.append(
            {
                "jurisdiction_code": row.jurisdiction_code,
                "status_canonical": None,
                "well_count": sum(classes.values()),
            }
        )
        # The vocabulary's classes at whatever this jurisdiction holds of them, zero included,
        # plus any class the data holds that no vocabulary names -- a bucket is never dropped
        # for being unexpected, which is the whole of what went wrong here.
        appended += [
            {
                "jurisdiction_code": row.jurisdiction_code,
                "status_canonical": status,
                "well_count": classes.get(status, 0),
            }
            for status in sorted({*vocabulary, *classes})
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
            # The class a null status is counted under, so the run names the decision rather
            # than leaving a reader to infer it from a word in the rows.
            "null_status_class": UNMAPPED_CLASS,
            # Which classes were measured, so a zero row resolves to a run that says it looked
            # for that class rather than to one that happened not to find it.
            "measured_classes": sorted(vocabulary),
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


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Append today's jurisdiction well-count measurement to the ledger."
    )
    parser.add_argument("--dsn", required=True)
    parser.add_argument(
        "--codes",
        default=None,
        help="comma-separated jurisdiction codes; the default measures every registration",
    )
    parser.add_argument("--env-id", default=None, help="override the fingerprinted env id")
    parser.add_argument("--code-version", default=None)
    arguments = parser.parse_args(argv)
    # No --measured-on. The ledger's date is the day the measurement was taken, and a flag that
    # moved it is the one edit an append-only ledger cannot survive.
    codes = (
        tuple(code.strip() for code in arguments.codes.split(",") if code.strip())
        if arguments.codes
        else None
    )

    with psycopg.connect(arguments.dsn) as connection:
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
