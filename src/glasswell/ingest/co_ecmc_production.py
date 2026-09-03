"""ECMC production into staging, resolved against each file's own header.

Colorado publishes a rolling file and twenty-seven annual archives, and exactly one of the
archives spells three columns differently, moves a fourth, writes ISO timestamps and uses the
literal string NULL. `cr_co_production_schema_drift_1` is the row that registers those aliases;
this module reads them and resolves every file's columns by name, never by position, because a
positional parse reads one file's water volumes as another's flared gas.

Staging is the terminus. No canonical write happens here.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import httpx
import psycopg

from glasswell.db.dsn import add_dsn_argument, resolve_dsn
from glasswell.ingest.base import IngestRun, open_ingest_run, resolve_environment
from glasswell.lineage.capture import derive
from glasswell.lineage.conformance import load_rules, rule_for_family
from glasswell.lineage.fetch import fetch_raw
from glasswell.lineage.fetch_attempts import durable_fetch_attempts
from glasswell.lineage.models import InputRef, OutputSpec
from glasswell.lineage.serialization import hash_payload

__rule_version__ = "1"

DOWNLOAD_ROOT = "https://ecmc.state.co.us/documents/data/downloads/production"
ROLLING_SOURCE_ID = "co_ecmc_monthly_prod"
ARCHIVE_SOURCE_ID = "co_ecmc_prod_reports"
ROLLING_KEY = "monthly_prod.csv"
STAGING_TABLE = "staging.co_ecmc_production"
MEDIA_TYPE = "text/csv"
DRIFT_FAMILY = "cr_co_production_schema_drift"
VINTAGE_FAMILY = "cr_co_production_vintage"
ROLLING = "rolling"
COPY_BATCH = 20_000


class SchemaDrift(ValueError):
    """A header this parse cannot resolve. Named columns, so the refusal is actionable."""


@dataclass(frozen=True, slots=True)
class LoadReport:
    source_id: str
    source_key: str
    manifest_id: str
    rows_staged: int
    columns: int

    def to_dict(self) -> dict[str, object]:
        return {
            "source_id": self.source_id,
            "source_key": self.source_key,
            "manifest_id": self.manifest_id,
            "rows_staged": self.rows_staged,
            "columns": self.columns,
        }


class ColumnResolver:
    """Header names to their position, under the registered aliases. Never ordinal."""

    def __init__(self, *, aliases: Mapping[str, Sequence[str]], null_tokens: Sequence[str]):
        self._canonical = {name.lower(): name.lower() for name in aliases}
        for name, spellings in aliases.items():
            for spelling in spellings:
                self._canonical[spelling.lower()] = name.lower()
        self._null_tokens = {token.strip().lower() for token in null_tokens}

    def canonical(self, name: str) -> str:
        return self._canonical.get(name.strip().lower(), name.strip().lower())

    def resolve(self, header: Sequence[str]) -> dict[str, int]:
        """Column name to index, refusing a header this staging table cannot hold."""
        resolved: dict[str, int] = {}
        # The refusal names the source's own spelling, which is the string an operator has to
        # go and look for; the resolved name would send them looking for a column ECMC never
        # wrote.
        unknown: list[str] = []
        for index, name in enumerate(header):
            canonical = self.canonical(name)
            resolved[canonical] = index
            if canonical not in STAGING_COLUMNS:
                unknown.append(name.strip())
        if unknown:
            raise SchemaDrift(
                f"{', '.join(sorted(unknown))} is not a registered ECMC production column;"
                f" register the spelling on {DRIFT_FAMILY}_1 rather than staging a column"
                " nothing declares"
            )
        missing = sorted(set(STAGING_COLUMNS) - set(resolved))
        if missing:
            raise SchemaDrift(f"the header declares no {', '.join(missing)}")
        return resolved

    def value(self, raw: str | None) -> str | None:
        if raw is None:
            return None
        text = raw.strip()
        return None if text.lower() in self._null_tokens else text


# The staged column set, which is the rolling file's spelling. The drifted archive's three
# alternative spellings resolve onto these before anything is written.
STAGING_COLUMNS: tuple[str, ...] = (
    "docnum", "reportmonth", "reportyear", "daysproduced", "accepteddate", "revised",
    "opname", "opnumber", "facilityid", "apicountycode", "apisequencenumber", "apisidetrack",
    "well", "wellstatus", "formationcode", "oilproduced", "oilsales", "oiladjustment",
    "oilgravity", "gasproduced", "gassales", "gasbtusales", "gasusedonlease", "gasshrinkage",
    "gaspressuretubing", "gaspressurecasing", "waterproduced", "waterpressuretubing",
    "waterpressurecasing", "flaredvented", "bominvent", "eominvent",
)


def accepted_date(
    raw: str | None, formats: Sequence[str], null_tokens: Sequence[str]
) -> date | None:
    """AcceptedDate under both registered formats. An unreadable one is refused, not nulled."""
    if raw is None or raw.strip().lower() in {token.strip().lower() for token in null_tokens}:
        return None
    text = raw.strip()
    for pattern in formats:
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            continue
    raise ValueError(
        f"{text} matches none of the registered AcceptedDate formats {list(formats)}"
    )


def source_key_for(selector: str) -> str:
    return ROLLING_KEY if selector == ROLLING else f"{selector}_prod_reports.csv"


def source_id_for(selector: str) -> str:
    return ROLLING_SOURCE_ID if selector == ROLLING else ARCHIVE_SOURCE_ID


def url_for(selector: str) -> str:
    return f"{DOWNLOAD_ROOT}/{source_key_for(selector)}"


def _resolver(run: IngestRun) -> tuple[ColumnResolver, list[str], list[str]]:
    """One header rule for both sources: the drift is a difference BETWEEN the files, so a copy
    of it filed under each would be two rules that could disagree about one measurement."""
    rules = load_rules(
        run.connection, source_id=ROLLING_SOURCE_ID, stage="parse", as_of=run.as_of
    )
    drift = rule_for_family(rules, DRIFT_FAMILY)
    aliases = {str(name): list(spellings) for name, spellings in drift.spec["aliases"].items()}
    null_tokens = [str(token) for token in drift.spec["null_tokens"]]
    formats = [str(pattern) for pattern in drift.spec["date_formats"]]
    return ColumnResolver(aliases=aliases, null_tokens=null_tokens), formats, [drift.rule_id]


def staged_rows(
    payload: Path, resolver: ColumnResolver, formats: Sequence[str], *, manifest_id: str
) -> Iterator[tuple[object, ...]]:
    """One tuple per source row, in the staging table's own column order."""
    with payload.open(newline="", encoding="latin-1") as handle:
        reader = csv.reader(handle)
        header = next(reader)
        index = resolver.resolve(header)
        for ordinal, row in enumerate(reader, start=1):
            if len(row) != len(header):
                raise SchemaDrift(
                    f"source row {ordinal} has {len(row)} fields against the header's"
                    f" {len(header)}"
                )
            values = [resolver.value(row[index[column]]) for column in STAGING_COLUMNS]
            # Read for its side effect: an unreadable accepted date is a refusal, and the
            # column is staged verbatim beside it so the raw text survives the parse.
            accepted_date(values[STAGING_COLUMNS.index("accepteddate")], formats, [])
            yield (manifest_id, ordinal, *values)


def _copy(connection: psycopg.Connection, rows: Iterable[tuple[object, ...]]) -> int:
    columns = ", ".join(("manifest_id", "source_row_ordinal", *STAGING_COLUMNS))
    written = 0
    with (
        connection.cursor() as cursor,
        cursor.copy(f"copy {STAGING_TABLE} ({columns}) from stdin") as copy,
    ):
        for row in rows:
            copy.write_row(row)
            written += 1
    return written


def _already_staged(connection: psycopg.Connection, manifest_id: str) -> int:
    with connection.cursor() as cursor:
        cursor.execute(
            f"select count(*) from {STAGING_TABLE} where manifest_id = %s", (manifest_id,)
        )
        return int(cursor.fetchone()[0])


def load(
    run: IngestRun,
    selector: str = ROLLING,
    *,
    url: str | None = None,
    client: httpx.Client | None = None,
) -> LoadReport:
    """Fetch one production file and stage it under the rules that resolve its columns."""
    connection = run.connection
    source_id = source_id_for(selector)
    source_key = source_key_for(selector)
    resolver, formats, cited = _resolver(run)
    # The vintage rule decides what an ARCHIVE filename's year means, so it is cited on an
    # archive load and not on the rolling file, which has no year in its name to misread.
    if selector != ROLLING:
        cited = [
            *cited,
            rule_for_family(
                load_rules(
                    connection, source_id=ARCHIVE_SOURCE_ID, stage="parse", as_of=run.as_of
                ),
                VINTAGE_FAMILY,
            ).rule_id,
        ]
    fetched = fetch_raw(
        connection,
        source_id,
        source_key,
        url=url or url_for(selector),
        raw_root=run.raw_root,
        client=client,
        media_type=MEDIA_TYPE,
        rules=cited,
    )
    manifest = fetched.manifest
    with derive(
        "stage.parse",
        output=OutputSpec(
            store="postgis",
            dataset=STAGING_TABLE,
            partition={"manifest_id": manifest.manifest_id},
        ),
        params={"source_key": source_key, "selector": selector, "columns": len(STAGING_COLUMNS)},
        inputs=[
            InputRef(
                kind="manifest",
                ref_id=manifest.manifest_id,
                role="primary",
                as_of_vintage=manifest.fetch_vintage,
            )
        ],
        rules=cited,
    ) as parsing:
        staged = _already_staged(connection, manifest.manifest_id)
        if not staged:
            staged = _copy(
                connection,
                staged_rows(
                    fetched.payload_path, resolver, formats, manifest_id=manifest.manifest_id
                ),
            )
        parsing.set_rows(staged)
        parsing.set_output_hash(
            hash_payload({"rows": staged, "manifest_id": manifest.manifest_id})
        )
    return LoadReport(
        source_id=source_id,
        source_key=source_key,
        manifest_id=manifest.manifest_id,
        rows_staged=staged,
        columns=len(STAGING_COLUMNS),
    )


def selectors(argument: str) -> tuple[str, ...]:
    """`rolling`, a year, or `all`. `all` is the archive backfill and is its own dispatch."""
    if argument != "all":
        return (argument,)
    return (ROLLING, *(str(year) for year in range(1999, 2026)))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Stage an ECMC production file. Staging is the terminus."
    )
    add_dsn_argument(parser)
    parser.add_argument(
        "--file",
        default=ROLLING,
        help="rolling, a four-digit archive year, or all (the backfill; its own dispatch)",
    )
    parser.add_argument("--raw-root", default=None)
    parser.add_argument("--env-id", default=None)
    parser.add_argument("--code-version", default=None)
    arguments = parser.parse_args(argv)
    arguments.dsn = resolve_dsn(arguments.dsn)

    reports: list[dict[str, object]] = []
    with durable_fetch_attempts(arguments.dsn), psycopg.connect(arguments.dsn) as connection:
        environment = resolve_environment(
            connection, env_id=arguments.env_id, code_version=arguments.code_version
        )
        for selector in selectors(arguments.file):
            with open_ingest_run(
                connection,
                source_id=source_id_for(selector),
                raw_root=arguments.raw_root,
                environment=environment,
            ) as run:
                reports.append(load(run, selector).to_dict())
            connection.commit()
    print(json.dumps(reports, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
