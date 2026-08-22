"""Load the RRC Wellbore Query export: TX well identity and the lease keys (SB-01 §2.9).

This is the identity half of the TX slice. It writes `canonical.wells` — operator, well name,
status, depth, completion date — and `canonical.well_lease_links`, which captures the
well-to-lease keys the future allocation join needs. It writes no production and no volume of
any kind: TX reports at the lease, and DIR-3 keeps an allocated series out of canonical.

The export ships 59 comma-separated fields and no header row, so the layout is
`cr_tx_ewa_layout_1` and is proved against every record before anything is promoted.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

import httpx
import polars as pl
import psycopg

from glasswell.ingest.base import record_vintage_day, resolve_environment
from glasswell.ingest.tx_mft import MftClient
from glasswell.lineage import (
    ConformanceRule,
    InputRef,
    OutputSpec,
    PostgresRecorder,
    apply_rules,
    current_session,
    derive,
    fetch_raw,
    lineage_session,
    load_rules,
    quarantine,
)
from glasswell.lineage.audit import emit
from glasswell.lineage.errors import RuleSpecError
from glasswell.lineage.serialization import hash_payload, json_ready

SOURCE_ID = "tx_wellbore_ewa_csv"
SOURCE_KEY = "OG_WELLBORE_EWA_Report.csv"
EWA_LINK = "https://mft.rrc.texas.gov/link/650649b7-e019-4d77-a8e0-d118d6455381"
STAGING_TABLE = "staging.tx_wellbore_ewa"
LAYOUT_RULE = "cr_tx_ewa_layout_1"
SCOPE_RULE = "cr_tx_ewa_scope_1"
LEASE_KEY_RULE = "cr_tx_lease_key_1"
API10_RULE = "cr_tx_api10_build_1"
PLUGGED_RULE = "cr_tx_plugged_precedence_1"
ROLE_RULE = "cr_tx_ewa_role_1"
COLLAPSE_RULE = "cr_tx_identity_collapse_1"
STATUS_FAMILY = "cr_tx_status_vocab"
BATCH_ROWS = 20_000

REASON_CODES = (
    "schema_mismatch", "key_incomplete", "unknown_status", "multi_completion",
)


@dataclass(frozen=True, slots=True)
class WellboreLoad:
    manifest_id: str
    parse_derivation_id: str
    identity_derivation_id: str
    links_derivation_id: str
    staged_rows: int
    excluded_rows: int
    wells: int
    lease_links: int
    quarantined: Mapping[str, int]
    status_coverage: float = 0.0
    unchanged: bool = False
    counties: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": SOURCE_ID,
            "manifest_id": self.manifest_id,
            "staged_rows": self.staged_rows,
            "excluded_rows": self.excluded_rows,
            "wells": self.wells,
            "lease_links": self.lease_links,
            "status_coverage": round(self.status_coverage, 4),
            "quarantined": dict(self.quarantined),
            "unchanged": self.unchanged,
        }


def rule(connection: psycopg.Connection, rule_id: str, source_id: str = SOURCE_ID
         ) -> ConformanceRule:
    for candidate in load_rules(connection, source_id=source_id):
        if candidate.rule_id == rule_id:
            return candidate
    raise LookupError(f"rule {rule_id} is not seeded for {source_id}")


def _layout(rule_spec: Mapping[str, Any]) -> dict[str, int]:
    """Field numbers are the manual's, one-based; the reader works in list indices."""
    return {name: int(position) - 1 for name, position in rule_spec["fields"].items()}


def _assert_layout(record: Sequence[str], layout: Mapping[str, int], spec: Mapping[str, Any]
                   ) -> str | None:
    """Prove the pin on this record. A layout that has just been disproved is not applied."""
    if len(record) != int(spec["field_count"]):
        return f"{len(record)} fields, layout declares {spec['field_count']}"
    assertions = spec.get("assertions", {})
    prefix = assertions.get("county_code_is_api_prefix")
    if prefix:
        county = record[int(prefix["county_code"]) - 1]
        api = record[int(prefix["api"]) - 1]
        if api[: int(prefix["width"])] != county:
            return f"county {county!r} is not the prefix of API {api!r}"
    domain = assertions.get("oil_gas_code_domain")
    if domain is not None and record[layout["oil_gas_code"]].strip() not in set(domain):
        return f"oil/gas code {record[layout['oil_gas_code']]!r} is outside the declared domain"
    return None


def _records(payload_path: Path) -> Iterator[list[str]]:
    with payload_path.open("r", newline="", encoding="utf-8", errors="replace") as handle:
        yield from csv.reader(handle)


def _stage(
    connection: psycopg.Connection,
    payload_path: Path,
    manifest_id: str,
    *,
    layout_rule: ConformanceRule,
    scope_rule: ConformanceRule,
) -> tuple[str, int, int, dict[str, int]]:
    layout = _layout(layout_rule.spec)
    counties = {str(code) for code in scope_rule.spec["county_codes"]}
    county_index = layout["county_code"]

    staged = 0
    excluded = 0
    rejected: list[dict[str, Any]] = []
    batch: list[tuple[str, int, list[str]]] = []
    statement = (
        f"insert into {STAGING_TABLE} (manifest_id, source_row_ordinal, fields)"
        " values (%s, %s, %s) on conflict (manifest_id, source_row_ordinal) do nothing"
    )
    with connection.cursor() as cursor:
        for ordinal, record in enumerate(_records(payload_path)):
            # Layout first, scope second. A record that has disproved the layout has not told
            # us which county it is in either, so scoping it out would hide a parse failure.
            note = _assert_layout(record, layout, layout_rule.spec)
            if note is not None:
                rejected.append(
                    {"source_row_ordinal": ordinal, "detail": note, "fields": len(record)}
                )
                continue
            if record[county_index] not in counties:
                # Not a reject: the record is outside the county scope this run was made under,
                # and its count reaches the derivation and an audit event.
                excluded += 1
                continue
            batch.append((manifest_id, ordinal, record))
            staged += 1
            if len(batch) >= BATCH_ROWS:
                cursor.executemany(statement, batch)
                batch.clear()
        if batch:
            cursor.executemany(statement, batch)

    output = OutputSpec(
        store="postgres", dataset=STAGING_TABLE, partition={"manifest_id": manifest_id}
    )
    with derive(
        "stage.parse",
        output=output,
        params={
            "layout_rule": layout_rule.rule_id,
            "scope_rule": scope_rule.rule_id,
            "field_count": int(layout_rule.spec["field_count"]),
            "counties_in_scope": len(counties),
            "rows_excluded_out_of_scope": excluded,
        },
        inputs=[InputRef(kind="manifest", ref_id=manifest_id)],
        rules=[layout_rule.rule_id, scope_rule.rule_id],
    ) as context:
        context.set_rows(staged)
        context.set_output_hash(hash_payload({"rows": staged, "manifest_id": manifest_id}))

    session = current_session()
    emit(
        connection,
        "staging.scope_excluded",
        subject_type="manifest",
        subject_id=manifest_id,
        payload={
            "rows_excluded": excluded,
            "rows_staged": staged,
            "scope_rule": scope_rule.rule_id,
            "counties_in_scope": sorted(counties),
        },
        correlation_id=session.correlation_id,
        occurred_at=session.clock.now(),
    )
    quarantined = {
        "schema_mismatch": _quarantine(
            connection,
            _quarantine_frame(rejected),
            manifest_id=manifest_id,
            reason_code="schema_mismatch",
            stage="parse",
            rule_id=layout_rule.rule_id,
        )
    }
    return context.derivation_id, staged, excluded, quarantined


def _quarantine_frame(rows: list[dict[str, Any]]) -> pl.DataFrame:
    """Scan every row for the schema; a late column value must not fail the whole batch."""
    return pl.DataFrame(rows, infer_schema_length=None)


def _quarantine(
    connection: psycopg.Connection,
    rows: pl.DataFrame,
    *,
    manifest_id: str,
    reason_code: str,
    stage: str,
    rule_id: str | None = None,
) -> int:
    if rows.is_empty():
        return 0
    session = current_session()
    quarantine(
        connection,
        rows,
        reason_code=reason_code,
        manifest_id=manifest_id,
        source_id=SOURCE_ID,
        staging_table=STAGING_TABLE,
        stage=stage,
        seen_at=session.clock.now(),
        rule_id=rule_id,
        correlation_id=session.correlation_id,
    )
    return rows.height


_STAGED = f"""
select source_row_ordinal, fields
  from {STAGING_TABLE}
 where manifest_id = %s
 order by source_row_ordinal
"""


def _frame(
    connection: psycopg.Connection, manifest_id: str, layout: Mapping[str, int], state_code: str
) -> pl.DataFrame:
    columns = {name: [] for name in layout}  # type: ignore[var-annotated]
    ordinals: list[int] = []
    with connection.cursor(name="tx_ewa_staged") as cursor:
        cursor.itersize = BATCH_ROWS
        cursor.execute(_STAGED, (manifest_id,))
        for ordinal, fields in cursor:
            ordinals.append(ordinal)
            for name, index in layout.items():
                columns[name].append(fields[index].strip())
    frame = pl.DataFrame(
        {"source_row_ordinal": ordinals, **columns},
        schema={
            "source_row_ordinal": pl.Int32,
            **dict.fromkeys(layout, pl.String),
        },
    )
    return frame.with_columns(pl.lit(state_code, dtype=pl.String).alias("state_code"))


def _status_input(frame: pl.DataFrame, precedence: ConformanceRule) -> pl.DataFrame:
    """A plugging date outranks the type field, and the sentinel it writes is the rule's."""
    plug = str(precedence.spec["precedence_field"])
    token = str(precedence.spec["precedence_token"])
    target = str(precedence.spec["target_field"])
    return frame.with_columns(
        pl.when(pl.col(plug).str.strip_chars().str.len_chars() > 0)
        .then(pl.lit(token))
        .otherwise(pl.col("well_type_name"))
        .alias(target)
    )


def _date(value: str | None) -> date | None:
    text = (value or "").strip()
    if len(text) != 8 or not text.isdigit():
        return None
    try:
        return datetime.strptime(text, "%Y%m%d").date()
    except ValueError:  # a source date of 20260231 is not a date, and is not promoted as one
        return None


def _depth(value: str | None) -> float | None:
    text = (value or "").strip()
    return float(text) if text.replace(".", "", 1).isdigit() and text else None


_INSERT_WELL = """
insert into canonical.wells (
    api10, state_code, county_code_at_permit, operator_name_reported, operator_id, well_name,
    status_canonical, status_reported, well_type_reported, total_depth_ft, completion_date,
    basin, effective_from, source_manifest_id, derivation_id)
values (%(api10)s, %(state_code)s, %(county_code)s, %(operator_name)s, %(operator_no)s,
        %(well_name)s, %(status_canonical)s, %(status_reported)s, %(well_type)s, %(depth)s,
        %(completion_date)s, %(basin)s, %(effective_from)s, %(manifest_id)s, %(derivation_id)s)
on conflict (api10, effective_from) do nothing
"""

_INSERT_LINK = """
insert into canonical.well_lease_links (
    api10, lease_key, oil_gas_code, district_no, lease_no, lease_name, well_no, field_no,
    field_name, link_role, source_id, effective_from, source_manifest_id, derivation_id)
values (%(api10)s, %(lease_key)s, %(oil_gas_code)s, %(district_no)s, %(lease_no)s,
        %(lease_name)s, %(well_no)s, %(field_no)s, %(field_name)s, %(link_role)s, %(source_id)s,
        %(effective_from)s, %(manifest_id)s, %(derivation_id)s)
on conflict (api10, lease_key, source_id, effective_from) do nothing
"""

BASIN = "permian"


_PREFERENCE_TESTS: Mapping[str, Callable[[Mapping[str, Any]], int]] = {
    "plug_date": lambda row: 0 if row["plug_date"] else 1,
    "on_schedule": lambda row: 0 if row["on_schedule"] == "Y" else 1,
    "completion_date": lambda row: 0 if row["completion_date"] else 1,
    "source_row_ordinal": lambda row: int(row["source_row_ordinal"]),
}


def _preference_order(collapse: ConformanceRule) -> tuple[str, ...]:
    """The tie-break is rule data (R8), so the order is read rather than written here."""
    declared = tuple(str(name) for name in collapse.spec.get("prefer") or ())
    unjudgeable = [name for name in declared if name not in _PREFERENCE_TESTS]
    if not declared or unjudgeable:
        raise RuleSpecError(
            f"{collapse.rule_id}: prefer is {list(declared)};"
            f" this promotion can judge {sorted(_PREFERENCE_TESTS)}"
        )
    return declared


def _preference(row: Mapping[str, Any], order: Sequence[str]) -> tuple[int, ...]:
    return tuple(_PREFERENCE_TESTS[name](row) for name in order)


def _identity_rows(
    frame: pl.DataFrame, order: Sequence[str]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """One identity row per API-10, and the export's further records for that wellbore.

    canonical.wells models the wellbore, and the export lists one once per completion, lease
    and field. The records that lose are completions, not evidence of a second wellbore, and
    they leave under cr_tx_identity_collapse_1 saying so; whether an API-10 really carries more
    than one wellbore is measured on the RRC's own wellbore codes in the GIS layers.

    Which record wins is the rule's `prefer` order, not this function's: a plugging date is
    ranked first there because cr_tx_plugged_precedence_1 makes that date the well's status,
    and a record discarded here is a record that rule never reads.
    """
    chosen: dict[str, dict[str, Any]] = {}
    extra: list[dict[str, Any]] = []
    for row in frame.iter_rows(named=True):
        api10 = row["api10"]
        held = chosen.get(api10)
        if held is None:
            chosen[api10] = row
            continue
        if _preference(row, order) < _preference(held, order):
            chosen[api10] = row
            extra.append(held)
        else:
            extra.append(row)
    return list(chosen.values()), extra


def load(
    connection: psycopg.Connection,
    *,
    url: str | None = None,
    raw_root: Path | str | None = None,
    client: httpx.Client | None = None,
    restage: bool = False,
) -> WellboreLoad:
    """Fetch the export, stage it under the pinned layout, and promote identity and links."""
    layout_rule = rule(connection, LAYOUT_RULE)
    scope_rule = rule(connection, SCOPE_RULE)
    lease_rule = rule(connection, LEASE_KEY_RULE)
    api10_rule = rule(connection, API10_RULE, source_id="tx_gis_wells_county")
    precedence = rule(connection, PLUGGED_RULE)
    role_rule = rule(connection, ROLE_RULE)
    collapse_rule = rule(connection, COLLAPSE_RULE)
    status_rules = [
        candidate
        for candidate in load_rules(connection, source_id=SOURCE_ID, stage="conform")
        if candidate.rule_family == STATUS_FAMILY
    ]
    if not status_rules:
        raise LookupError(f"no active rule in family {STATUS_FAMILY}")

    fetched = fetch_raw(
        connection,
        SOURCE_ID,
        SOURCE_KEY,
        url=url or f"{EWA_LINK}?filename={SOURCE_KEY}",
        acquisition_method="mft_guid_resolve",
        raw_root=raw_root,
        client=client,
        media_type="text/csv",
    )
    manifest = fetched.manifest
    if restage:
        with connection.cursor() as cursor:
            cursor.execute(
                f"delete from {STAGING_TABLE} where manifest_id = %s", (manifest.manifest_id,)
            )
    elif _already_promoted(connection, manifest.manifest_id):
        return WellboreLoad(
            manifest_id=manifest.manifest_id,
            parse_derivation_id="",
            identity_derivation_id="",
            links_derivation_id="",
            staged_rows=0,
            excluded_rows=0,
            wells=0,
            lease_links=0,
            quarantined=dict.fromkeys(REASON_CODES, 0),
            unchanged=True,
        )

    parse_id, staged, excluded, counts = _stage(
        connection,
        fetched.payload_path,
        manifest.manifest_id,
        layout_rule=layout_rule,
        scope_rule=scope_rule,
    )
    counts = {**dict.fromkeys(REASON_CODES, 0), **counts}

    layout = _layout(layout_rule.spec)
    frame = _frame(connection, manifest.manifest_id, layout, str(api10_rule.spec["state_code"]))
    # The API-10 rule runs over everything; the lease key runs only on the link path. A well
    # whose permit carries no lease number yet is still a well, and quarantining its identity
    # for a key it does not need loses whole counties: 68,806 of the 2026-08 export's in-scope
    # records have no lease number, including every record Bailey and El Paso counties have.
    keyed = apply_rules(frame, [api10_rule])
    for batch in keyed.quarantined:
        counts[batch.reason_code] = counts.get(batch.reason_code, 0) + _quarantine(
            connection,
            batch.frame,
            manifest_id=manifest.manifest_id,
            reason_code=batch.reason_code,
            stage="join",
            rule_id=batch.rule_id,
        )

    identity, extra = _identity_rows(
        _status_input(keyed.frame, precedence), _preference_order(collapse_rule)
    )
    counts["multi_completion"] += _quarantine(
        connection,
        _quarantine_frame(extra),
        manifest_id=manifest.manifest_id,
        reason_code="multi_completion",
        stage="validate",
        rule_id=collapse_rule.rule_id,
    )

    # A blank type is not an unknown one: the source reported nothing, so the row keeps a null
    # status rather than being quarantined for a vocabulary it never used.
    reported = pl.DataFrame(
        [row for row in identity if row["status_input"]],
        schema={**dict.fromkeys(layout, pl.String), "source_row_ordinal": pl.Int32,
                "state_code": pl.String, "api10": pl.String, "status_input": pl.String},
    )
    silent = [row for row in identity if not row["status_input"]]
    mapped = apply_rules(reported, status_rules)
    for batch in mapped.quarantined:
        counts[batch.reason_code] = counts.get(batch.reason_code, 0) + _quarantine(
            connection,
            batch.frame,
            manifest_id=manifest.manifest_id,
            reason_code=batch.reason_code,
            stage="conform",
            rule_id=batch.rule_id,
        )
    promoted = [
        *mapped.frame.to_dicts(),
        *[{**row, "status_canonical": None} for row in silent],
    ]

    identity_id = _promote_identity(
        connection,
        promoted,
        manifest_id=manifest.manifest_id,
        vintage=manifest.fetch_vintage,
        parse_derivation_id=parse_id,
        rules=[*keyed.applied_rule_ids, *mapped.applied_rule_ids, precedence.rule_id],
        state_code=str(api10_rule.spec["state_code"]),
    )
    leased = apply_rules(keyed.frame, [lease_rule])
    for batch in leased.quarantined:
        counts[batch.reason_code] = counts.get(batch.reason_code, 0) + _quarantine(
            connection,
            batch.frame,
            manifest_id=manifest.manifest_id,
            reason_code=batch.reason_code,
            stage="join",
            rule_id=batch.rule_id,
        )
    links_id, links = _promote_lease_links(
        connection,
        leased.frame,
        manifest_id=manifest.manifest_id,
        vintage=manifest.fetch_vintage,
        parse_derivation_id=parse_id,
        role_rule=role_rule,
        lease_rule=lease_rule,
    )
    # A same-day restage upserts the same (source, day) ledger row — accumulate onto it
    # rather than overwriting the pass that did the work (DR-85).
    record_vintage_day(
        connection,
        source_id=SOURCE_ID,
        vintage_date=manifest.fetch_vintage,
        manifest_ids=[manifest.manifest_id],
        opened_at=current_session().clock.now(),
        promotion_derivation_id=identity_id,
        rows_examined=staged,
        rows_appended=len(promoted),
    )
    with_status = sum(1 for row in promoted if row.get("status_canonical"))
    return WellboreLoad(
        manifest_id=manifest.manifest_id,
        parse_derivation_id=parse_id,
        identity_derivation_id=identity_id,
        links_derivation_id=links_id,
        staged_rows=staged,
        excluded_rows=excluded,
        wells=len(promoted),
        lease_links=links,
        quarantined=counts,
        status_coverage=with_status / len(promoted) if promoted else 0.0,
        counties=tuple(sorted({row["county_code"] for row in promoted})),
    )


def _already_promoted(connection: psycopg.Connection, manifest_id: str) -> bool:
    with connection.cursor() as cursor:
        cursor.execute(
            "select 1 from canonical.wells where source_manifest_id = %s limit 1", (manifest_id,)
        )
        return cursor.fetchone() is not None


def _promote_identity(
    connection: psycopg.Connection,
    rows: Sequence[Mapping[str, Any]],
    *,
    manifest_id: str,
    vintage: date,
    parse_derivation_id: str,
    rules: Sequence[str],
    state_code: str,
) -> str:
    payload = [
        {
            "api10": row["api10"],
            "state_code": row["state_code"],
            "county_code": row["county_code"],
            "operator_name": row["operator_name"] or None,
            "operator_no": row["operator_no"] or None,
            "well_name": " ".join(
                part for part in (row["lease_name"], row["well_no"]) if part
            ) or None,
            "status_canonical": row.get("status_canonical"),
            # One RRC field is both: WELL_TYPE_NAME is what the wellbore is used for, and it is
            # the field cr_tx_status_vocab_1 maps. Where a plugging date outranked it the
            # reported value still stands as written and the rule explains the difference.
            "status_reported": row["well_type_name"] or None,
            "well_type": row["well_type_name"] or None,
            "depth": _depth(row["total_depth_ft"]),
            "completion_date": _date(row["completion_date"]),
            "basin": BASIN,
            "effective_from": vintage,
            "manifest_id": manifest_id,
        }
        for row in rows
    ]
    with derive(
        "canonical.promote",
        output=OutputSpec(
            store="postgres",
            dataset="canonical.wells",
            partition={"manifest_id": manifest_id, "state": "TX"},
        ),
        params={"layer": "identity", "state_code": state_code, "basin": BASIN},
        inputs=[
            InputRef(kind="derivation", ref_id=parse_derivation_id),
            InputRef(kind="manifest", ref_id=manifest_id, as_of_vintage=vintage),
        ],
        rules=list(dict.fromkeys(rules)),
    ) as context:
        context.set_rows(len(payload))
        context.set_output_hash(
            hash_payload(json_ready({"api10s": sorted(row["api10"] for row in payload)}))
        )
    with connection.cursor() as cursor:
        cursor.executemany(
            _INSERT_WELL,
            [{**row, "derivation_id": context.derivation_id} for row in payload],
        )
    return context.derivation_id


def _promote_lease_links(
    connection: psycopg.Connection,
    frame: pl.DataFrame,
    *,
    manifest_id: str,
    vintage: date,
    parse_derivation_id: str,
    role_rule: ConformanceRule,
    lease_rule: ConformanceRule,
) -> tuple[str, int]:
    """Every well-to-lease pair the crosswalk states, under the role that says which crosswalk."""
    link_role = str(role_rule.spec["link_role"])
    seen: set[tuple[str, str]] = set()
    payload: list[dict[str, Any]] = []
    for row in frame.iter_rows(named=True):
        key = (row["api10"], row["lease_key"])
        if key in seen:
            continue
        seen.add(key)
        payload.append(
            {
                "api10": row["api10"],
                "lease_key": row["lease_key"],
                "oil_gas_code": row["oil_gas_code"],
                "district_no": row["district_no"],
                "lease_no": row["lease_no"],
                "lease_name": row["lease_name"] or None,
                "well_no": row["well_no"] or None,
                "field_no": row["field_no"] or None,
                "field_name": row["field_name"] or None,
                "link_role": link_role,
                "source_id": SOURCE_ID,
                "effective_from": vintage,
                "manifest_id": manifest_id,
            }
        )
    with derive(
        "canonical.promote",
        output=OutputSpec(
            store="postgres",
            dataset="canonical.well_lease_links",
            partition={"manifest_id": manifest_id, "link_role": link_role},
        ),
        params={"link_role": link_role, "merge_forbidden": True},
        inputs=[
            InputRef(kind="derivation", ref_id=parse_derivation_id),
            InputRef(kind="manifest", ref_id=manifest_id, as_of_vintage=vintage),
        ],
        rules=[lease_rule.rule_id, role_rule.rule_id],
    ) as context:
        context.set_rows(len(payload))
        context.set_output_hash(
            hash_payload(json_ready({"links": sorted(f"{a}/{k}" for a, k in sorted(seen))}))
        )
    with connection.cursor() as cursor:
        cursor.executemany(
            _INSERT_LINK, [{**row, "derivation_id": context.derivation_id} for row in payload]
        )
    return context.derivation_id, len(payload)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Load the TX RRC wellbore query export into staging and canonical."
    )
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--url", default=None, help="override the resolved URL (testing only)")
    parser.add_argument("--raw-root", default=None)
    parser.add_argument("--env-id", default=None, help="override the fingerprinted env id")
    parser.add_argument("--code-version", default=None)
    parser.add_argument(
        "--restage", action="store_true", help="re-parse from the stored bytes after a rule change"
    )
    arguments = parser.parse_args(argv)

    with psycopg.connect(arguments.dsn) as connection:
        environment = resolve_environment(
            connection, env_id=arguments.env_id, code_version=arguments.code_version
        )
        with lineage_session(recorder=PostgresRecorder(connection), environment=environment):
            if arguments.url:
                result = load(
                    connection, url=arguments.url, raw_root=arguments.raw_root,
                    restage=arguments.restage,
                )
            else:
                with MftClient(EWA_LINK) as mft:
                    result = load(
                        connection,
                        url=mft.url_for(SOURCE_KEY),
                        client=mft.client,
                        raw_root=arguments.raw_root,
                        restage=arguments.restage,
                    )
        connection.commit()
    print(json.dumps(result.to_dict(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
