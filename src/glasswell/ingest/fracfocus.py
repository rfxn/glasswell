"""Ingest FracFocus disclosures as defensible ND completion anchors."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, TextIO
from zipfile import ZipFile

import httpx
import polars as pl
import psycopg
from psycopg.rows import dict_row

from glasswell.ingest.base import open_ingest_run, record_vintage_day
from glasswell.lineage import InputRef, OutputSpec, current_session, derive, fetch_raw, quarantine
from glasswell.lineage.fetch_attempts import durable_fetch_attempts
from glasswell.lineage.serialization import hash_payload, json_ready
from glasswell.seed.conformance_fracfocus import DOWNLOAD_URL, TERMS_URL

SOURCE_ID = "fracfocus_csv"
SOURCE_KEY = "FracFocusCSV.zip"
TERMS_KEY = "terms.html"
DISCLOSURE_MEMBER = "DisclosureList_1.csv"
PARSE_RULE_ID = "cr_ff_disclosure_parse_1"
IDENTITY_RULE_ID = "cr_ff_api_identity_1"
ANCHOR_RULE_ID = "cr_ff_completion_anchor_1"
BASIN_RULE_ID = "cr_nd_basin_1"
ANCHOR_KIND = "hydraulic_frac_job_end"
STAGING_TABLE = "staging.fracfocus_disclosures"

_API_DIGITS = re.compile(r"\D")
_DATE_FORMATS = ("%m/%d/%Y %I:%M:%S %p", "%m/%d/%Y", "%Y-%m-%d")
_SOURCE_COLUMNS = (
    "DisclosureId",
    "JobStartDate",
    "JobEndDate",
    "APINumber",
    "StateName",
    "CountyName",
    "OperatorName",
    "WellName",
    "Latitude",
    "Longitude",
    "Projection",
    "TVD",
    "TotalBaseWaterVolume",
    "TotalBaseNonWaterVolume",
    "FFVersion",
    "FederalWell",
    "IndianWell",
)
_STAGING_COLUMNS = (
    "disclosure_id",
    "job_start_date",
    "job_end_date",
    "api_number",
    "state_name",
    "county_name",
    "operator_name",
    "well_name",
    "latitude",
    "longitude",
    "projection",
    "tvd",
    "total_base_water_volume",
    "total_base_non_water_volume",
    "ff_version",
    "federal_well",
    "indian_well",
)


class FracFocusSchemaDrift(ValueError):
    """The disclosure member no longer carries the pinned source columns."""


class ReadinessVintageCollision(RuntimeError):
    """Another source already wrote the current effective-dated well revision."""


@dataclass(frozen=True, slots=True)
class FracFocusLoadResult:
    manifest_id: str
    terms_manifest_id: str
    parse_derivation_id: str
    anchor_derivation_id: str
    readiness_derivation_id: str
    staged_rows: int
    anchor_rows: int
    well_rows: int
    quarantined: Mapping[str, int]
    unchanged: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "manifest_id": self.manifest_id,
            "terms_manifest_id": self.terms_manifest_id,
            "staged_rows": self.staged_rows,
            "anchor_rows": self.anchor_rows,
            "well_rows": self.well_rows,
            "quarantined": dict(self.quarantined),
            "unchanged": self.unchanged,
        }


def zip_inventory(path: Path) -> list[dict[str, Any]]:
    """Hash decompressed ZIP members without materialising them beside the raw artifact."""
    inventory: list[dict[str, Any]] = []
    with ZipFile(path) as archive:
        for member in sorted(archive.infolist(), key=lambda item: item.filename):
            digest = hashlib.sha256()
            size = 0
            with archive.open(member) as stream:
                for chunk in iter(lambda: stream.read(1 << 20), b""):
                    digest.update(chunk)
                    size += len(chunk)
            inventory.append(
                {
                    "member": member.filename,
                    "bytes": size,
                    "compressed_bytes": member.compress_size,
                    "sha256": digest.hexdigest(),
                }
            )
    return inventory


def normalize_api10(value: str | None) -> str | None:
    digits = _API_DIGITS.sub("", value or "")
    if len(digits) != 14:
        return None
    return digits[:10]


def parse_source_date(value: str | None) -> date | None:
    raw = (value or "").strip()
    if not raw:
        return None
    for pattern in _DATE_FORMATS:
        try:
            return datetime.strptime(raw, pattern).date()
        except ValueError:
            continue
    raise ValueError(f"unsupported FracFocus timestamp {raw!r}")


def load_disclosures(
    connection: psycopg.Connection,
    *,
    raw_root: Path | str | None = None,
    client: httpx.Client | None = None,
) -> FracFocusLoadResult:
    """Fetch, stage, and promote the disclosure header needed for ND completion anchors."""
    owned_client = client is None
    session = client or httpx.Client(
        follow_redirects=True,
        timeout=900.0,
        headers={"User-Agent": "glasswell public-data-ingest"},
    )
    try:
        terms = fetch_raw(
            connection,
            SOURCE_ID,
            TERMS_KEY,
            url=TERMS_URL,
            raw_root=raw_root,
            client=session,
            media_type="text/html",
            license_note="FracFocus Terms and Conditions captured before archive acquisition.",
        )
        accepted_at = current_session().clock.now().isoformat()
        fetched = fetch_raw(
            connection,
            SOURCE_ID,
            SOURCE_KEY,
            url=DOWNLOAD_URL,
            acquisition_method="click_wall_accept",
            raw_root=raw_root,
            client=session,
            rules=[PARSE_RULE_ID],
            media_type="application/zip",
            license_note=(
                "FracFocus terms captured as a separate immutable manifest; archive bytes are"
                " unaltered and redistribution is not asserted."
            ),
            extra_acquisition_params={
                "terms_url": TERMS_URL,
                "terms_sha256": terms.manifest.sha256,
                "terms_manifest_id": terms.manifest.manifest_id,
                "accepted_at": accepted_at,
            },
            decompressed_inventory=zip_inventory,
        )
    finally:
        if owned_client:
            session.close()

    manifest = fetched.manifest
    if fetched.unchanged and _already_staged(connection, manifest.manifest_id):
        parse_id, anchor_id, readiness_id = _existing_derivations(
            connection, manifest.manifest_id
        )
        return FracFocusLoadResult(
            manifest_id=manifest.manifest_id,
            terms_manifest_id=terms.manifest.manifest_id,
            parse_derivation_id=parse_id,
            anchor_derivation_id=anchor_id,
            readiness_derivation_id=readiness_id,
            staged_rows=0,
            anchor_rows=0,
            well_rows=0,
            quarantined={
                "parse_error": 0,
                "out_of_range_date": 0,
                "orphan_fk": 0,
                "duplicate_row": 0,
            },
            unchanged=True,
        )

    parse_id, staged_rows = _stage_disclosures(
        connection, fetched.payload_path, manifest.manifest_id
    )
    anchor_id, anchor_rows, quarantined = _promote_anchors(
        connection,
        manifest_id=manifest.manifest_id,
        vintage=manifest.fetch_vintage,
        parse_derivation_id=parse_id,
    )
    readiness_id, well_rows = materialize_nd_readiness(
        connection,
        manifest_id=manifest.manifest_id,
        vintage=manifest.fetch_vintage,
        anchor_derivation_id=anchor_id,
    )
    record_vintage_day(
        connection,
        source_id=SOURCE_ID,
        vintage_date=manifest.fetch_vintage,
        manifest_ids=[terms.manifest.manifest_id, manifest.manifest_id],
        opened_at=current_session().clock.now(),
        promotion_derivation_id=anchor_id,
        rows_examined=staged_rows,
        rows_appended=anchor_rows,
    )
    return FracFocusLoadResult(
        manifest_id=manifest.manifest_id,
        terms_manifest_id=terms.manifest.manifest_id,
        parse_derivation_id=parse_id,
        anchor_derivation_id=anchor_id,
        readiness_derivation_id=readiness_id,
        staged_rows=staged_rows,
        anchor_rows=anchor_rows,
        well_rows=well_rows,
        quarantined=quarantined,
    )


def _already_staged(connection: psycopg.Connection, manifest_id: str) -> bool:
    with connection.cursor() as cursor:
        cursor.execute(
            "select 1 from staging.fracfocus_disclosures where manifest_id = %s limit 1",
            (manifest_id,),
        )
        return cursor.fetchone() is not None


def _existing_derivations(
    connection: psycopg.Connection, manifest_id: str
) -> tuple[str, str, str]:
    with connection.cursor() as cursor:
        cursor.execute(
            "select output_dataset, derivation_id from lineage.derivations"
            " where output_partition ->> 'manifest_id' = %s"
            "   and output_dataset in (%s, %s, %s)",
            (
                manifest_id,
                STAGING_TABLE,
                "canonical.well_completion_anchors",
                "canonical.wells",
            ),
        )
        found = dict(cursor.fetchall())
    return (
        found.get(STAGING_TABLE, ""),
        found.get("canonical.well_completion_anchors", ""),
        found.get("canonical.wells", ""),
    )


def _disclosure_reader(archive: ZipFile) -> tuple[TextIO, csv.DictReader]:
    names = [member.filename for member in archive.infolist()]
    if names.count(DISCLOSURE_MEMBER) != 1:
        raise FracFocusSchemaDrift(
            f"expected one {DISCLOSURE_MEMBER}, found {names.count(DISCLOSURE_MEMBER)}"
        )
    text = archive.open(DISCLOSURE_MEMBER)
    wrapper = io.TextIOWrapper(text, encoding="utf-8-sig", newline="")
    reader = csv.DictReader(wrapper)
    if tuple(reader.fieldnames or ()) != _SOURCE_COLUMNS:
        wrapper.close()
        raise FracFocusSchemaDrift(
            f"{DISCLOSURE_MEMBER} headers are {reader.fieldnames!r}, expected {_SOURCE_COLUMNS!r}"
        )
    return wrapper, reader


def _stage_disclosures(
    connection: psycopg.Connection, path: Path, manifest_id: str
) -> tuple[str, int]:
    output = OutputSpec(
        store="postgres", dataset=STAGING_TABLE, partition={"manifest_id": manifest_id}
    )
    rows = 0
    with derive(
        "stage.parse",
        output=output,
        params={"member": DISCLOSURE_MEMBER, "encoding": "utf-8-sig", "all_columns": "text"},
        inputs=[InputRef(kind="manifest", ref_id=manifest_id)],
        rules=[PARSE_RULE_ID],
    ) as context, ZipFile(path) as archive:
        wrapper, reader = _disclosure_reader(archive)
        try:
            statement = (
                "copy staging.fracfocus_disclosures (manifest_id, source_row_ordinal, "
                + ", ".join(_STAGING_COLUMNS)
                + ") from stdin"
            )
            with connection.cursor() as cursor, cursor.copy(statement) as copy:
                for rows, source_row in enumerate(reader, start=1):
                    copy.write_row(
                        (
                            manifest_id,
                            rows,
                            *(source_row[column] for column in _SOURCE_COLUMNS),
                        )
                    )
        finally:
            wrapper.close()
        context.set_rows(rows)
        context.set_output_hash(hash_payload({"manifest_id": manifest_id, "rows": rows}))
    return context.derivation_id, rows


def _candidate_rows(connection: psycopg.Connection, manifest_id: str) -> list[dict[str, Any]]:
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            "select source_row_ordinal, disclosure_id, job_start_date, job_end_date,"
            " api_number, state_name from staging.fracfocus_disclosures"
            " where manifest_id = %s"
            "   and (state_name = 'North Dakota' or api_number like '33%%')"
            " order by source_row_ordinal",
            (manifest_id,),
        )
        return [dict(row) for row in cursor.fetchall()]


def _current_nd_api10s(connection: psycopg.Connection) -> set[str]:
    with connection.cursor() as cursor:
        cursor.execute("select api10 from canonical.wells_latest where state_code = '33'")
        return {row[0] for row in cursor.fetchall()}


def _quarantine_rows(
    connection: psycopg.Connection,
    rows: list[dict[str, Any]],
    *,
    manifest_id: str,
    reason_code: str,
    rule_id: str,
) -> int:
    if not rows:
        return 0
    session = current_session()
    quarantine(
        connection,
        pl.DataFrame(rows, infer_schema_length=None),
        reason_code=reason_code,
        manifest_id=manifest_id,
        source_id=SOURCE_ID,
        staging_table=STAGING_TABLE,
        stage="conform",
        seen_at=session.clock.now(),
        rule_id=rule_id,
        correlation_id=session.correlation_id,
    )
    return len(rows)


_INSERT_ANCHOR = """
insert into canonical.well_completion_anchors
    (disclosure_id, api10, job_start_date, completion_date, anchor_kind, source_id,
     report_vintage, source_manifest_id, derivation_id)
values (%(disclosure_id)s, %(api10)s, %(job_start_date)s, %(completion_date)s,
        %(anchor_kind)s, %(source_id)s, %(report_vintage)s, %(manifest_id)s,
        %(derivation_id)s)
on conflict do nothing
"""


def _promote_anchors(
    connection: psycopg.Connection,
    *,
    manifest_id: str,
    vintage: date,
    parse_derivation_id: str,
) -> tuple[str, int, dict[str, int]]:
    known = _current_nd_api10s(connection)
    valid: list[dict[str, Any]] = []
    malformed_identity: list[dict[str, Any]] = []
    malformed_date: list[dict[str, Any]] = []
    chronology: list[dict[str, Any]] = []
    orphans: list[dict[str, Any]] = []
    duplicates: list[dict[str, Any]] = []
    disclosure_ids: set[str] = set()
    for row in _candidate_rows(connection, manifest_id):
        api10 = normalize_api10(row["api_number"])
        try:
            start = parse_source_date(row["job_start_date"])
            end = parse_source_date(row["job_end_date"])
        except ValueError as error:
            malformed_date.append({**row, "detail": str(error)})
            continue
        if (
            not row["disclosure_id"]
            or api10 is None
            or not api10.startswith("33")
            or row["state_name"] != "North Dakota"
            or end is None
        ):
            malformed_identity.append(
                {**row, "detail": "missing or inconsistent anchor identity"}
            )
            continue
        if start is not None and end < start:
            chronology.append({**row, "detail": "JobEndDate precedes JobStartDate"})
            continue
        if api10 not in known:
            orphans.append({**row, "api10": api10, "detail": "API-10 absent from OGD wells"})
            continue
        if row["disclosure_id"] in disclosure_ids:
            duplicates.append({**row, "detail": "duplicate DisclosureId in one archive"})
            continue
        disclosure_ids.add(row["disclosure_id"])
        valid.append(
            {
                "disclosure_id": row["disclosure_id"],
                "api10": api10,
                "job_start_date": start,
                "completion_date": end,
                "anchor_kind": ANCHOR_KIND,
                "source_id": SOURCE_ID,
                "report_vintage": vintage,
                "manifest_id": manifest_id,
            }
        )

    quarantined = {
        "parse_error": _quarantine_rows(
            connection,
            malformed_identity,
            manifest_id=manifest_id,
            reason_code="parse_error",
            rule_id=IDENTITY_RULE_ID,
        )
        + _quarantine_rows(
            connection,
            malformed_date,
            manifest_id=manifest_id,
            reason_code="parse_error",
            rule_id=ANCHOR_RULE_ID,
        ),
        "out_of_range_date": _quarantine_rows(
            connection,
            chronology,
            manifest_id=manifest_id,
            reason_code="out_of_range_date",
            rule_id=ANCHOR_RULE_ID,
        ),
        "orphan_fk": _quarantine_rows(
            connection,
            orphans,
            manifest_id=manifest_id,
            reason_code="orphan_fk",
            rule_id=IDENTITY_RULE_ID,
        ),
        "duplicate_row": _quarantine_rows(
            connection,
            duplicates,
            manifest_id=manifest_id,
            reason_code="duplicate_row",
            rule_id=IDENTITY_RULE_ID,
        ),
    }

    output = OutputSpec(
        store="postgres",
        dataset="canonical.well_completion_anchors",
        partition={"manifest_id": manifest_id},
    )
    with derive(
        "canonical.promote",
        output=output,
        params={
            "state": "North Dakota",
            "anchor_kind": ANCHOR_KIND,
            "source_field": "JobEndDate",
        },
        inputs=[
            InputRef(kind="derivation", ref_id=parse_derivation_id),
            InputRef(kind="manifest", ref_id=manifest_id, as_of_vintage=vintage),
        ],
        rules=[IDENTITY_RULE_ID, ANCHOR_RULE_ID],
    ) as context:
        context.set_rows(len(valid))
        context.set_output_hash(hash_payload(json_ready(valid)))
    with connection.cursor() as cursor:
        cursor.executemany(
            _INSERT_ANCHOR,
            [{**row, "derivation_id": context.derivation_id} for row in valid],
        )
        inserted = max(cursor.rowcount, 0)
    return context.derivation_id, inserted, quarantined


_CURRENT_WELLS = """
select api10, api14, state_code, county_code_at_permit, ndic_file_no, operator_name_reported,
       operator_id, well_name, status_canonical, status_reported, well_type_reported, spud_date,
       confidential_flag, basin, land_unit_label, effective_from, source_manifest_id,
       total_depth_ft, completion_date
  from canonical.wells_latest
 where state_code = '33'
 order by api10
"""

_INSERT_WELL_REVISION = """
insert into canonical.wells
    (api10, api14, state_code, county_code_at_permit, ndic_file_no, operator_name_reported,
     operator_id, well_name, status_canonical, status_reported, well_type_reported, spud_date,
     confidential_flag, basin, land_unit_label, effective_from, source_manifest_id,
     derivation_id, total_depth_ft, completion_date)
values
    (%(api10)s, %(api14)s, %(state_code)s, %(county_code_at_permit)s, %(ndic_file_no)s,
     %(operator_name_reported)s, %(operator_id)s, %(well_name)s, %(status_canonical)s,
     %(status_reported)s, %(well_type_reported)s, %(spud_date)s, %(confidential_flag)s,
     %(basin)s, %(land_unit_label)s, %(effective_from)s, %(source_manifest_id)s,
     %(derivation_id)s, %(total_depth_ft)s, %(completion_date)s)
on conflict (api10, effective_from) do nothing
"""


def materialize_nd_readiness(
    connection: psycopg.Connection,
    *,
    manifest_id: str,
    vintage: date,
    anchor_derivation_id: str,
) -> tuple[str, int]:
    """Append a current ND well revision with basin and earliest valid frac-job end."""
    with connection.cursor() as cursor:
        cursor.execute(
            "select api10, min(completion_date) from canonical.well_completion_anchors_latest"
            " where source_id = %s group by api10",
            (SOURCE_ID,),
        )
        anchors = dict(cursor.fetchall())
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(_CURRENT_WELLS)
        current = [dict(row) for row in cursor.fetchall()]

    updates: list[dict[str, Any]] = []
    collisions: list[str] = []
    for row in current:
        anchored = anchors.get(row["api10"])
        completion_date = anchored if anchored is not None else row["completion_date"]
        if row["basin"] == "williston" and row["completion_date"] == completion_date:
            continue
        if row["effective_from"] >= vintage:
            collisions.append(row["api10"])
            continue
        updates.append(
            {
                **row,
                "basin": "williston",
                "completion_date": completion_date,
                "effective_from": vintage,
                "source_manifest_id": (
                    manifest_id if anchored is not None else row["source_manifest_id"]
                ),
            }
        )
    if collisions:
        raise ReadinessVintageCollision(
            f"{len(collisions)} ND wells already have an effective row at {vintage};"
            f" first API-10 is {collisions[0]}"
        )

    output = OutputSpec(
        store="postgres", dataset="canonical.wells", partition={"manifest_id": manifest_id}
    )
    with derive(
        "canonical.promote",
        output=output,
        params={
            "state_code": "33",
            "basin": "williston",
            "completion_selection": "earliest_valid_job_end_per_api10",
        },
        inputs=[
            InputRef(kind="derivation", ref_id=anchor_derivation_id),
            InputRef(
                kind="external",
                ref_id="canonical.wells_latest",
                as_of_vintage=vintage,
                role="crosswalk",
            ),
        ],
        rules=[BASIN_RULE_ID, ANCHOR_RULE_ID],
    ) as context:
        context.set_rows(len(updates))
        context.set_output_hash(
            hash_payload(
                [
                    {
                        "api10": row["api10"],
                        "basin": row["basin"],
                        "completion_date": row["completion_date"],
                    }
                    for row in updates
                ]
            )
        )
    with connection.cursor() as cursor:
        cursor.executemany(
            _INSERT_WELL_REVISION,
            [{**row, "derivation_id": context.derivation_id} for row in updates],
        )
        inserted = max(cursor.rowcount, 0)
    if inserted != len(updates):
        raise ReadinessVintageCollision(
            f"attempted {len(updates)} ND well revisions but inserted {inserted}"
        )
    return context.derivation_id, inserted


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest FracFocus ND completion anchors.")
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--raw-root")
    arguments = parser.parse_args(argv)
    with durable_fetch_attempts(arguments.dsn), psycopg.connect(
        arguments.dsn
    ) as connection, open_ingest_run(
        connection, source_id=SOURCE_ID, raw_root=arguments.raw_root
    ) as run:
        result = load_disclosures(run.connection, raw_root=run.raw_root)
        connection.commit()
    print(json.dumps(result.to_dict(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
