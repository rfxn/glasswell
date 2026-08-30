"""New Mexico well headers and their surface geometry, promoted from the staged header table.

This is the phase that opens the New Mexico gate. `api/routers/wells.py` roots the spine on
`canonical.wells`, so every New Mexico production row already resident becomes servable the
instant the first prefix-30 header lands here, and nowhere earlier.

The header table ships latitude, longitude and datum, which the production table does not — so
New Mexico geometry needs no second source. It ships them as a *pair* that has to be judged as a
pair: `ST_MakePoint` consumes both and raises on neither, so four records with a good New Mexico
latitude and a longitude of exactly zero would otherwise acquire a perfectly valid point in the
Gulf of Guinea, in an append-only table, on a published tile layer.

No state code appears in this module. The `30` lives in `cr_nm_wellhistory_api10_1`'s spec and
is read from the registry, as `nm_ocd.py` does it.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date
from typing import Any

import polars as pl
import psycopg

from glasswell.ingest.base import (
    IngestRun,
    open_ingest_run,
    record_vintage_day,
    resolve_environment,
)
from glasswell.ingest.nm_dims import RowCountMismatch, SchemaDrift
from glasswell.ingest.nm_ocd import (
    UNREGISTERED_REASON,
    head_manifest,
    source_id_for,
    staging_table_for,
)
from glasswell.lineage.audit import emit
from glasswell.lineage.capture import derive
from glasswell.lineage.conformance import (
    ConformanceRule,
    QuarantineBatch,
    apply_rules,
    load_rules,
    rule_for_family,
)
from glasswell.lineage.errors import VintageAlreadyPromoted
from glasswell.lineage.models import InputRef, ManifestRecord, OutputSpec
from glasswell.lineage.quarantine import quarantine
from glasswell.lineage.serialization import hash_payload
from glasswell.seed.conformance_nm import NM_COLUMNS

__rule_version__ = "1"

HEADER_TABLE = "wellhistory"
OPERATOR_TABLE = "ogrid"
CANONICAL_WELLS = "canonical.wells"
CANONICAL_SPATIAL = "canonical.well_spatial"

API10_FAMILY = "cr_nm_wellhistory_api10"
EFFECTIVE_FAMILY = "cr_nm_wellhistory_effective"
STATUS_FAMILY = "cr_nm_wellhistory_status_vocab"
WELL_TYPE_FAMILY = "cr_nm_wellhistory_well_type"
DATUM_FAMILY = "cr_nm_wellhistory_datum"
COORDINATE_FAMILY = "cr_nm_wellhistory_coordinate"
PROVENANCE_FAMILY = "cr_nm_wellhistory_geometry_provenance"
SCOPE_FAMILY = "cr_nm_wellhistory_geometry_scope"
PRECEDENCE_FAMILY = "cr_nm_wellhistory_header_precedence"

BATCH_ROWS = 50_000
QUARANTINE_CAP = 60_000
OUTCOME = "__glasswell_coordinate_outcome"
LATITUDE = "latitude"
LONGITUDE = "longitude"
PROMOTE = "promote"

HEADER_COLUMNS: tuple[str, ...] = (
    "api10",
    "state_code",
    "county_code_at_permit",
    "operator_id",
    "operator_name_reported",
    "well_name",
    "status_reported",
    "well_type_reported",
    "spud_date",
    "effective_from",
)
SPATIAL_COLUMNS: tuple[str, ...] = ("api10", LONGITUDE, LATITUDE, "effective_from")

_CREATE_HEADER_BATCH = """
create temporary table nm_well_header_batch (
    api10                  text not null,
    state_code             text,
    county_code_at_permit  text,
    operator_id            text,
    operator_name_reported text,
    well_name              text,
    status_reported        text,
    well_type_reported     text,
    spud_date              date,
    effective_from         date not null
) on commit drop
"""

_CREATE_SPATIAL_BATCH = """
create temporary table nm_well_spatial_batch (
    api10          text not null,
    longitude      double precision not null,
    latitude       double precision not null,
    effective_from date not null
) on commit drop
"""

# One row per (api10, effective_from); the source files a header per effective date and a well
# with two effective rows is two headers, which is what an effective-dated table is for.
_APPEND_HEADERS = f"""
insert into {CANONICAL_WELLS} (
    api10, state_code, county_code_at_permit, operator_id, operator_name_reported, well_name,
    status_reported, status_canonical, well_type_reported, spud_date, effective_from,
    source_manifest_id, derivation_id)
select distinct on (b.api10, b.effective_from)
       b.api10, b.state_code, b.county_code_at_permit, b.operator_id, b.operator_name_reported,
       b.well_name, b.status_reported, null, b.well_type_reported, b.spud_date, b.effective_from,
       %(manifest_id)s, %(derivation_id)s
  from nm_well_header_batch b
 where not exists (
       select 1 from {CANONICAL_WELLS} w
        where w.api10 = b.api10 and w.effective_from = b.effective_from)
 order by b.api10, b.effective_from
"""

# The transform is explicit and the rule that authorised it is stored beside the geometry, so a
# point can never reach storage in the source frame without a row saying which rule moved it.
_APPEND_SPATIAL = f"""
insert into {CANONICAL_SPATIAL} (
    api10, geom_type, geom_key, geom, source_datum, transform_rule_id, source_manifest_id,
    derivation_id)
select distinct on (b.api10)
       b.api10, %(geom_type)s, %(geom_key)s,
       st_transform(st_setsrid(st_makepoint(b.longitude, b.latitude), %(source_epsg)s),
                    %(target_epsg)s),
       %(source_datum)s, %(transform_rule_id)s, %(manifest_id)s, %(derivation_id)s
  from nm_well_spatial_batch b
 where not exists (
       select 1 from {CANONICAL_SPATIAL} s
        where s.api10 = b.api10 and s.geom_type = %(geom_type)s and s.geom_key = %(geom_key)s)
 order by b.api10, b.effective_from desc
"""

# A same-vintage re-run recomputes an answer or it refuses; it never rewrites one. The key is
# what the anti-join above already agrees on, so the compare is on the attributes.
_HEADER_DIVERGENCE = f"""
select count(*), min(w.api10 || ' ' || w.effective_from::text)
  from {CANONICAL_WELLS} w
  join nm_well_header_batch b
    on b.api10 = w.api10 and b.effective_from = w.effective_from
 where (w.state_code, w.county_code_at_permit, w.operator_id, w.well_name, w.status_reported,
        w.well_type_reported, w.spud_date)
    is distinct from
       (b.state_code, b.county_code_at_permit, b.operator_id, b.well_name, b.status_reported,
        b.well_type_reported, b.spud_date)
"""

_OPERATOR_NAMES = """
select operator_raw, operator from lineage.operator_aliases where source_id = %(source_id)s
"""


@dataclass(frozen=True, slots=True)
class HeaderReport:
    source_id: str
    report_vintage: date
    manifest_id: str
    staged_rows: int
    header_rows: int
    headers_appended: int
    geometry_rows: int
    geometry_appended: int
    quarantined: dict[str, int] = field(default_factory=dict)
    derivation_id: str = ""
    vintage_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "report_vintage": self.report_vintage.isoformat(),
            "manifest_id": self.manifest_id,
            "staged_rows": self.staged_rows,
            "header_rows": self.header_rows,
            "headers_appended": self.headers_appended,
            "geometry_rows": self.geometry_rows,
            "geometry_appended": self.geometry_appended,
            "quarantined": dict(sorted(self.quarantined.items())),
            "derivation_id": self.derivation_id,
            "vintage_id": self.vintage_id,
        }


def parse_ordinate(value: str | None) -> float | None:
    """The ordinate as a number, or None when the element was nil, absent or unreadable.

    Every non-nil ordinate in the artifact is scientific notation — 639,237 of 639,237 — so a
    parser that slices characters or assumes a decimal point fails on the whole file.
    """
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def classify_pair(
    latitude: float | None, longitude: float | None, *, precedence: Sequence[str] = ("nil", "zero")
) -> str:
    """`promote`, `coordinate_absent` or `coordinate_sentinel`, judged on the pair.

    Precedence comes from `cr_nm_wellhistory_coordinate_1`, because three records are nil on one
    ordinate and valued on the other, and two independent per-ordinate rules cannot say which
    outcome those take.
    """
    tests = {
        "nil": (latitude is None or longitude is None, "coordinate_absent"),
        "zero": (latitude == 0.0 or longitude == 0.0, "coordinate_sentinel"),
    }
    for name in precedence:
        failed, outcome = tests[name]
        if failed:
            return outcome
    return PROMOTE


def classify_frame(frame: pl.DataFrame, rule: ConformanceRule) -> pl.DataFrame:
    """Add the outcome column the coordinate rule defines, one value per record."""
    precedence = [str(item) for item in rule.spec.get("precedence") or ("nil", "zero")]
    outcomes = [
        classify_pair(
            parse_ordinate(row[LATITUDE]), parse_ordinate(row[LONGITUDE]), precedence=precedence
        )
        for row in frame.select(LATITUDE, LONGITUDE).iter_rows(named=True)
    ]
    return frame.with_columns(pl.Series(OUTCOME, outcomes, dtype=pl.String))


def _trimmed(column: str) -> pl.Expr:
    """Right-side only: leading spaces are data, trailing spaces are CHAR padding."""
    return pl.col(column).str.strip_chars_end(" ").replace("", None)


def _as_date(column: str) -> pl.Expr:
    return pl.col(column).str.slice(0, 10).str.to_date("%Y-%m-%d", strict=False)


def dated(frame: pl.DataFrame, rule: ConformanceRule) -> tuple[pl.DataFrame, pl.DataFrame]:
    """The records whose effective date reads, and the ones whose does not.

    The header key is (api10, effective_from), so a record with no readable eff_dte has no key.
    It is quarantined rather than dropped, and it is judged before the coordinate is, so the two
    reconciliations stay disjoint. The column is the one the rule names, not a literal here.
    """
    marked = frame.with_columns(
        _as_date(str(rule.spec["effective_from_field"])).alias("effective_from")
    )
    return (
        marked.filter(pl.col("effective_from").is_not_null()),
        marked.filter(pl.col("effective_from").is_null()).drop("effective_from"),
    )


def header_records(
    frame: pl.DataFrame, *, state_code: str, county_width: int, operators: Mapping[str, str]
) -> pl.DataFrame:
    """The canonical header columns, from the conformed and dated staging frame."""
    names = [operators.get((value or "").rstrip(" ")) for value in frame["ogrid_cde"].to_list()]
    return frame.with_columns(
        pl.lit(state_code).alias("state_code"),
        pl.col("api_cnty_cde").str.pad_start(county_width, "0").alias("county_code_at_permit"),
        _trimmed("ogrid_cde").alias("operator_id"),
        pl.Series("operator_name_reported", names, dtype=pl.String),
        _trimmed("well_name").alias("well_name"),
        _trimmed("status").alias("status_reported"),
        _trimmed("well_typ_cde").alias("well_type_reported"),
        _as_date("spud_dte").alias("spud_date"),
    )


def promote_headers(
    run: IngestRun,
    *,
    manifest: ManifestRecord | None = None,
    batch_rows: int = BATCH_ROWS,
) -> HeaderReport:
    """Promote the header table at the run's vintage: one derivation for the partition."""
    connection = run.connection
    source_id = source_id_for(HEADER_TABLE)
    head = manifest or head_manifest(connection, source_id)
    _require_columns(connection, HEADER_TABLE)

    rules = load_rules(connection, source_id=source_id, stage="conform", as_of=run.as_of)
    validate_rules = load_rules(connection, source_id=source_id, stage="validate", as_of=run.as_of)
    api10_rule = rule_for_family(rules, API10_FAMILY)
    datum_rule = rule_for_family(rules, DATUM_FAMILY)
    coordinate_rule = rule_for_family(validate_rules, COORDINATE_FAMILY)
    effective_rule = rule_for_family(rules, EFFECTIVE_FAMILY)
    cited = [
        api10_rule.rule_id,
        effective_rule.rule_id,
        rule_for_family(rules, STATUS_FAMILY).rule_id,
        rule_for_family(rules, WELL_TYPE_FAMILY).rule_id,
    ]
    spatial_cited = [
        datum_rule.rule_id,
        coordinate_rule.rule_id,
        rule_for_family(rules, PROVENANCE_FAMILY).rule_id,
        rule_for_family(rules, SCOPE_FAMILY).rule_id,
    ]
    precedence_rule = rule_for_family(
        load_rules(connection, source_id=source_id, stage="join", as_of=run.as_of),
        PRECEDENCE_FAMILY,
    )
    state_code = str(api10_rule.spec["state_code"])
    county_width = int(dict(api10_rule.spec["pad"])["api_cnty_cde"])
    operators = _operator_names(connection)
    vocabulary = _reason_vocabulary(connection)

    counts: dict[str, int] = {}
    staged_rows = 0
    header_rows = 0
    geometry_rows = 0
    digests: list[str] = []

    with derive(
        "canonical.promote",
        output=OutputSpec(
            store="postgres",
            dataset=CANONICAL_WELLS,
            partition={"source_id": source_id, "report_vintage": run.as_of.isoformat()},
        ),
        params={
            "coordinate_precedence": list(coordinate_rule.spec["precedence"]),
            "geom_types_produced": list(
                rule_for_family(rules, SCOPE_FAMILY).spec["geom_types_produced"]
            ),
            "header_authority": dict(precedence_rule.spec["authority"]),
            "source_epsg": int(datum_rule.spec["source_epsg"]),
            "target_epsg": int(datum_rule.spec["target_epsg"]),
        },
        inputs=[
            InputRef(
                kind="manifest",
                ref_id=head.manifest_id,
                role="primary",
                as_of_vintage=head.fetch_vintage,
            )
        ],
    ) as promotion:
        with connection.cursor() as cursor:
            cursor.execute(_CREATE_HEADER_BATCH)
            cursor.execute(_CREATE_SPATIAL_BATCH)

        for frame in _staged_frames(
            connection, manifest_id=head.manifest_id, batch_rows=batch_rows
        ):
            staged_rows += frame.height
            keyed = apply_rules(frame, [api10_rule])
            _route(run, keyed.quarantined, stage="conform", vocabulary=vocabulary, counts=counts,
                   manifest_id=head.manifest_id)
            keyed_and_dated, undated = dated(keyed.frame, effective_rule)
            if not undated.is_empty():
                _route(
                    run,
                    [
                        QuarantineBatch(
                            str(effective_rule.spec["reason_code"]),
                            effective_rule.rule_id,
                            undated,
                        )
                    ],
                    stage="conform", vocabulary=vocabulary, counts=counts,
                    manifest_id=head.manifest_id,
                )
            classified = classify_frame(keyed_and_dated, coordinate_rule)
            refused = [
                QuarantineBatch(
                    reason_code=outcome,
                    rule_id=coordinate_rule.rule_id,
                    frame=classified.filter(pl.col(OUTCOME) == outcome).drop(OUTCOME),
                )
                for outcome in ("coordinate_absent", "coordinate_sentinel")
            ]
            _route(run, [batch for batch in refused if not batch.frame.is_empty()],
                   stage="validate", vocabulary=vocabulary, counts=counts,
                   manifest_id=head.manifest_id)

            # A refused coordinate never suppresses the header: the well exists whether or not
            # the regulator filed a location for it.
            headers = header_records(
                classified, state_code=state_code, county_width=county_width, operators=operators
            )
            header_rows += headers.height
            digests.append(hash_payload(headers.select(HEADER_COLUMNS).rows()))
            _copy(connection, "nm_well_header_batch", headers, HEADER_COLUMNS)

            placeable = classified.filter(pl.col(OUTCOME) == PROMOTE)
            geometry = header_records(
                placeable, state_code=state_code, county_width=county_width, operators=operators
            ).with_columns(
                pl.Series(
                    LATITUDE,
                    [parse_ordinate(value) for value in placeable[LATITUDE].to_list()],
                    dtype=pl.Float64,
                ),
                pl.Series(
                    LONGITUDE,
                    [parse_ordinate(value) for value in placeable[LONGITUDE].to_list()],
                    dtype=pl.Float64,
                ),
            )
            geometry_rows += geometry.height
            _copy(connection, "nm_well_spatial_batch", geometry, SPATIAL_COLUMNS)

        parameters = {
            "manifest_id": head.manifest_id,
            "derivation_id": None,
            "geom_type": _geom_type(rules),
            "geom_key": _geom_type(rules),
            "source_epsg": int(datum_rule.spec["source_epsg"]),
            "target_epsg": int(datum_rule.spec["target_epsg"]),
            "source_datum": f"EPSG:{datum_rule.spec['source_epsg']}",
            "transform_rule_id": datum_rule.rule_id,
        }
        with connection.cursor() as cursor:
            cursor.execute("analyze nm_well_header_batch")
            cursor.execute("analyze nm_well_spatial_batch")
        _refuse_vintage_rewrite(connection)

        for rule_id in cited:
            promotion.add_rule(rule_id, applied_rows=header_rows)
        for rule_id in spatial_cited:
            promotion.add_rule(rule_id, applied_rows=geometry_rows)
        promotion.add_rule(precedence_rule.rule_id, applied_rows=header_rows)
        promotion.set_rows(header_rows)
        # What the batches computed, not what the store kept: hashing the appended subset would
        # make the derivation a function of prior state.
        promotion.set_output_hash(hash_payload(sorted(digests)))

    written = {**parameters, "derivation_id": promotion.derivation_id}
    headers_appended = _execute(connection, _APPEND_HEADERS, written)
    geometry_appended = _execute(connection, _APPEND_SPATIAL, written)

    # Two identities, each on counted populations rather than on subtraction, and disjoint by
    # construction: a record loses its key, then its date, then its coordinate, in that order.
    keyless = counts.get("key_incomplete", 0) + counts.get(UNREGISTERED_REASON, 0)
    if staged_rows != header_rows + keyless + counts.get("out_of_range_date", 0):
        raise RowCountMismatch(
            f"{CANONICAL_WELLS}: read {staged_rows} records but built {header_rows} headers with"
            f" {keyless} unkeyed and {counts.get('out_of_range_date', 0)} undated; a refused"
            " coordinate must never suppress a header"
        )
    refusals = counts.get("coordinate_absent", 0) + counts.get("coordinate_sentinel", 0)
    if header_rows != geometry_rows + refusals:
        raise RowCountMismatch(
            f"{CANONICAL_SPATIAL}: built {header_rows} headers but placed {geometry_rows} points"
            f" and refused {refusals}; a header is exactly one of those"
        )
    report = HeaderReport(
        source_id=source_id,
        report_vintage=run.as_of,
        manifest_id=head.manifest_id,
        staged_rows=staged_rows,
        header_rows=header_rows,
        headers_appended=headers_appended,
        geometry_rows=geometry_rows,
        geometry_appended=geometry_appended,
        quarantined=counts,
        derivation_id=promotion.derivation_id,
    )
    return _close_vintage(run, report)


def _geom_type(rules: Sequence[ConformanceRule]) -> str:
    produced = rule_for_family(rules, SCOPE_FAMILY).spec["geom_types_produced"]
    return str(next(iter(produced)))


def _operator_names(connection: psycopg.Connection) -> dict[str, str]:
    """The OGRID names the dimension promotion learned, if it has run. Reported, never required:
    an unresolved operator is a null name, not a refused header."""
    with connection.cursor() as cursor:
        cursor.execute(_OPERATOR_NAMES, {"source_id": source_id_for(OPERATOR_TABLE)})
        return {str(raw): str(name) for raw, name in cursor.fetchall()}


def _staged_frames(
    connection: psycopg.Connection, *, manifest_id: str, batch_rows: int
) -> Iterator[pl.DataFrame]:
    columns = ["source_row_ordinal", *NM_COLUMNS[HEADER_TABLE]]
    projection = ", ".join(f'"{name}"' for name in columns)
    statement = (
        f"select {projection} from {staging_table_for(HEADER_TABLE)}"
        " where manifest_id = %(manifest_id)s and source_row_ordinal >= %(after)s"
        " order by source_row_ordinal limit %(limit)s"
    )
    after = 0
    while True:
        with connection.cursor() as cursor:
            cursor.execute(
                statement, {"manifest_id": manifest_id, "after": after, "limit": batch_rows}
            )
            rows = cursor.fetchall()
        if not rows:
            return
        yield pl.DataFrame(rows, schema=columns, orient="row")
        after = int(rows[-1][0]) + 1


def _require_columns(connection: psycopg.Connection, table: str) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "select column_name from information_schema.columns"
            " where table_schema = 'staging' and table_name = %s",
            (staging_table_for(table).split(".", 1)[1],),
        )
        present = {name for (name,) in cursor.fetchall()}
    missing = [column for column in NM_COLUMNS[table] if column not in present]
    if missing:
        raise SchemaDrift(f"{staging_table_for(table)} does not carry {missing}")


def _route(
    run: IngestRun,
    batches: Sequence[QuarantineBatch],
    *,
    stage: str,
    vocabulary: frozenset[str],
    counts: dict[str, int],
    manifest_id: str,
) -> None:
    source_id = source_id_for(HEADER_TABLE)
    for batch in batches:
        reason = batch.reason_code if batch.reason_code in vocabulary else UNREGISTERED_REASON
        recorded = batch.frame.head(QUARANTINE_CAP)
        result = quarantine(
            run.connection,
            recorded,
            reason_code=reason,
            manifest_id=manifest_id,
            source_id=source_id,
            staging_table=staging_table_for(HEADER_TABLE),
            stage=stage,
            seen_at=run.session.clock.now(),
            rule_id=batch.rule_id,
            correlation_id=run.session.correlation_id,
        )
        counts[reason] = counts.get(reason, 0) + batch.frame.height
        emit(
            run.connection,
            "staging.rows_quarantined",
            subject_type="manifest",
            subject_id=manifest_id,
            payload={
                "staging_table": staging_table_for(HEADER_TABLE),
                "reason_code": reason,
                "rule_id": batch.rule_id,
                "rows": batch.frame.height,
                "recorded": recorded.height,
                "opened": result.opened,
                "reoccurred": result.reoccurred,
                "stage": stage,
            },
            correlation_id=run.session.correlation_id,
        )


def _copy(
    connection: psycopg.Connection,
    table: str,
    records: pl.DataFrame,
    columns: Sequence[str],
) -> None:
    if records.is_empty():
        return
    projection = ", ".join(f'"{name}"' for name in columns)
    with (
        connection.cursor() as cursor,
        cursor.copy(f"copy {table} ({projection}) from stdin") as copy,
    ):
        for row in records.select(list(columns)).iter_rows():
            copy.write_row(row)


def _execute(
    connection: psycopg.Connection, statement: str, parameters: Mapping[str, Any]
) -> int:
    with connection.cursor() as cursor:
        cursor.execute(statement, dict(parameters))
        return cursor.rowcount


def _refuse_vintage_rewrite(connection: psycopg.Connection) -> None:
    with connection.cursor() as cursor:
        cursor.execute(_HEADER_DIVERGENCE)
        rows, example = cursor.fetchone()
    if rows:
        raise VintageAlreadyPromoted(
            f"{CANONICAL_WELLS}: {rows} header(s) already promoted at this key carry different"
            f" attributes, the first being {example}. A restatement is a new effective row, not"
            " a rewrite of one already published"
        )


def _reason_vocabulary(connection: psycopg.Connection) -> frozenset[str]:
    from glasswell.ingest.nm_ocd import _reason_vocabulary as vocabulary

    return vocabulary(connection)


def _close_vintage(run: IngestRun, report: HeaderReport) -> HeaderReport:
    record = record_vintage_day(
        run.connection,
        source_id=report.source_id,
        vintage_date=report.report_vintage,
        manifest_ids=[report.manifest_id],
        opened_at=run.session.clock.now(),
        promotion_derivation_id=report.derivation_id,
        rows_examined=report.staged_rows,
        rows_appended=report.headers_appended,
    )
    if record is None:
        return report
    return replace(report, vintage_id=record.vintage_id)


def run_headers(
    connection: psycopg.Connection,
    *,
    batch_rows: int = BATCH_ROWS,
    env_id: str | None = None,
    code_version: str | None = None,
) -> HeaderReport:
    resolved = resolve_environment(connection, env_id=env_id, code_version=code_version)
    with open_ingest_run(
        connection, source_id=source_id_for(HEADER_TABLE), environment=resolved
    ) as run:
        return promote_headers(run, batch_rows=batch_rows)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Promote NM well headers and surface geometry from the staged header table."
    )
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--batch-rows", type=int, default=BATCH_ROWS)
    parser.add_argument("--env-id", default=None)
    parser.add_argument("--code-version", default=None)
    arguments = parser.parse_args(argv)

    connection = psycopg.connect(arguments.dsn)
    try:
        try:
            report = run_headers(
                connection,
                batch_rows=arguments.batch_rows,
                env_id=arguments.env_id,
                code_version=arguments.code_version,
            )
        except VintageAlreadyPromoted as refused:
            connection.rollback()
            print(f"refused: {refused}", flush=True)
            return 2
        connection.commit()
    finally:
        connection.close()
    print(json.dumps(report.to_dict(), sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
