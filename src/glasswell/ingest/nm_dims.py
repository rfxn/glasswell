"""New Mexico's completion dimension — the substrate D3's Validator B is built on.

`wchistory` is NM's own effective-dated history of the well-completion-x-pool entity the
production spine reports at, so the dimension is promoted from it rather than derived from the
spine: 426,529 observations over 147,975 completions, one open row each. Every observation is
appended, never updated, because a dimension that keeps only the current row cannot answer an
as-of question.

Three things about the source shape the module. `podwc` is many-to-many and stream-scoped, so a
completion in three PODs is three rows rather than one row with two PODs discarded. `spc_unit_idn`
'0' is the regulator's absent marker, not a spacing unit. And OGRID is an exact operator key, so
the alias load is a key copy at confidence 1.000 and there is no fuzzy pass anywhere in the path.

The unit of work is one manifest's staged rows read in batches, and the POD fan-out is a
server-side join: nothing here holds the corpus in Python.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import polars as pl
import psycopg

from glasswell.db.dsn import add_dsn_argument, resolve_dsn
from glasswell.ingest.base import (
    IngestRun,
    open_ingest_run,
    record_vintage_day,
    resolve_environment,
)
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
from glasswell.lineage.errors import RuleSpecError, VintageAlreadyPromoted
from glasswell.lineage.models import InputRef, ManifestRecord, OutputSpec
from glasswell.lineage.quarantine import quarantine
from glasswell.lineage.serialization import hash_payload
from glasswell.seed.conformance_nm import NM_COLUMNS

__rule_version__ = "1"

DIM_TABLE = "wchistory"
CROSSWALK_TABLE = "podwc"
OPERATOR_TABLE = "ogrid"
SPINE_TABLE = "wcproduction"
# The registries the promoted identifiers are counted against. Resolution is reported, never
# required: cr_nm_wchistory_lease_identifier_1 keeps a reference the registry has not caught up
# with rather than dropping grouping power the artifact does have.
REGISTRY_TABLES: tuple[str, ...] = ("pod", "spacingunit", "property")
SOURCE_TABLES: tuple[str, ...] = (
    DIM_TABLE,
    CROSSWALK_TABLE,
    OPERATOR_TABLE,
    *REGISTRY_TABLES,
)

CANONICAL_TABLE = "canonical.well_completions"
ALIAS_TABLE = "lineage.operator_aliases"

API10_FAMILY = "cr_nm_wchistory_api10"
COMPLETION_KEY_FAMILY = "cr_nm_wchistory_completion_key"
EFFECTIVE_FAMILY = "cr_nm_wchistory_effective"
WELLBORE_FAMILY = "cr_nm_wchistory_wellbore_policy"
STATUS_FAMILY = "cr_nm_wchistory_status_domain"
IDENTIFIER_FAMILY = "cr_nm_wchistory_lease_identifier"
POD_FAMILY = "cr_nm_podwc_pod"
REGISTRY_FAMILY = "cr_nm_ogrid_registry"
OPERATOR_FAMILY = "cr_nm_ogrid_operator"
LEASE_EQUIVALENT_FAMILY = "cr_nm_wcproduction_lease_equivalent"

OPERATOR_RAW = "operator_raw"
OPERATOR = "operator"
COMPLETION_KEY = "completion_key"
EFFECTIVE_FROM = "effective_from"
_ONSET = "__glasswell_pod_onset"
# One batch is the working set; 426,529 rows is five of them and the widest sibling table fits
# in one. The number is a memory bound, not a tuning knob.
BATCH_ROWS = 100_000
QUARANTINE_CAP = 60_000

# The columns the batch table and the canonical insert share, in one order.
DIMENSION_COLUMNS: tuple[str, ...] = (
    COMPLETION_KEY,
    "api10",
    "api12",
    "well_completion_pool",
    "pool_reported",
    "source_operator_key",
    "spacing_unit_id",
    "property_id",
    "status_reported",
    "status_canonical",
    EFFECTIVE_FROM,
)

# P5.7's structural probe: the shape lineage.vintages.select_production issues, with the api10
# bound. It is here rather than in the test so the plan under assertion is the served one.
SERVED_PRODUCTION_PROBE = """
select p.*, row_number() over (
           partition by entity_type, entity_key, production_month, stream, source_id
           order by report_vintage desc) as vintage_rank
  from canonical.production_monthly p
 where p.api10 = '3305301633'
"""


class SchemaDrift(RuntimeError):
    """The staged table does not carry the columns the dimension reads."""


class RowCountMismatch(RuntimeError):
    """A staged observation is promoted, quarantined or neither, and never two of them."""


@dataclass(frozen=True, slots=True)
class DimensionPolicy:
    """Every dimension decision, read out of the registry rather than written down here."""

    key_columns: Sequence[str]
    pool_column: str
    operator_column: str
    effective_from_field: str
    termination_field: str
    open_sentinel: str
    spacing_unit_field: str
    property_field: str
    absent_sentinels: tuple[str, ...]
    orphan_reason: str
    status_field: str
    wellbore_status: str
    wellbore_detection_field: str | None
    rule_ids: Mapping[str, str]

    @classmethod
    def from_rules(cls, rules: Sequence[ConformanceRule]) -> DimensionPolicy:
        def pinned(family: str) -> ConformanceRule:
            return rule_for_family(rules, family)

        key = pinned(API10_FAMILY)
        effective = pinned(EFFECTIVE_FAMILY)
        identifiers = pinned(IDENTIFIER_FAMILY)
        wellbore = pinned(WELLBORE_FAMILY)
        cited = (
            API10_FAMILY,
            COMPLETION_KEY_FAMILY,
            EFFECTIVE_FAMILY,
            WELLBORE_FAMILY,
            STATUS_FAMILY,
            IDENTIFIER_FAMILY,
        )
        return cls(
            key_columns=[str(column) for column in key.spec["source_cols"]],
            pool_column=str(pinned(COMPLETION_KEY_FAMILY).spec["source_cols"][1]),
            operator_column=str(pinned(REGISTRY_FAMILY).spec["operator_raw_field"]),
            effective_from_field=str(effective.spec["effective_from_field"]),
            termination_field=str(effective.spec["termination_field"]),
            open_sentinel=str(effective.spec["open_sentinel"]),
            spacing_unit_field=str(identifiers.spec["spacing_unit_field"]),
            property_field=str(identifiers.spec["property_field"]),
            absent_sentinels=tuple(str(token) for token in identifiers.spec["absent_sentinels"]),
            orphan_reason=str(identifiers.spec["reason_code"]),
            status_field=str(pinned(STATUS_FAMILY).spec["declares_fields"][0]),
            wellbore_status=str(wellbore.spec["status"]),
            wellbore_detection_field=(
                None
                if wellbore.spec["detection_field"] is None
                else str(wellbore.spec["detection_field"])
            ),
            rule_ids={family: pinned(family).rule_id for family in cited},
        )

    def cite(self, family: str) -> str:
        return self.rule_ids[family]


@dataclass(frozen=True, slots=True)
class DimensionReport:
    source_id: str
    report_vintage: date
    manifest_ids: Mapping[str, str]
    staged_rows: int = 0
    kept_completions: int = 0
    promoted_rows: int = 0
    aliases_written: int = 0
    aliases_registered: int = 0
    pod_fanout: int = 0
    wellbore_policy: str = "vacuous"
    quarantined: Mapping[str, int] = field(default_factory=dict)
    resolution: Mapping[str, int] = field(default_factory=dict)
    derivation_id: str = ""
    alias_derivation_id: str = ""
    vintage_id: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "source_id": self.source_id,
            "report_vintage": self.report_vintage.isoformat(),
            "manifest_ids": dict(self.manifest_ids),
            "staged_rows": self.staged_rows,
            "kept_completions": self.kept_completions,
            "promoted_rows": self.promoted_rows,
            "aliases_written": self.aliases_written,
            "aliases_registered": self.aliases_registered,
            "pod_fanout": self.pod_fanout,
            "wellbore_policy": self.wellbore_policy,
            "quarantined": dict(self.quarantined),
            "resolution": dict(self.resolution),
            "derivation_id": self.derivation_id,
            "alias_derivation_id": self.alias_derivation_id,
            "vintage_id": self.vintage_id,
        }


_CREATE_BATCH = """
create temp table nm_dimension_batch (
    completion_key       text not null,
    api10                text not null,
    api12                text,
    well_completion_pool text not null,
    pool_reported        text,
    source_operator_key  text,
    spacing_unit_id      text,
    property_id          text,
    status_reported      text,
    status_canonical     text,
    effective_from       date not null
) on commit drop
"""

# The crosswalk, keyed the way the dimension is keyed and indexed for the range predicate.
# Without it the lateral below re-scans 224,778 staged rows per observation, which at 426,529
# observations is not slow, it is a different order of magnitude.
_CREATE_CROSSWALK = """
create temp table nm_pod_crosswalk on commit drop as
select distinct
       api_st_cde || lpad(api_cnty_cde, 3, '0') || lpad(api_well_idn, 5, '0') as api10,
       pool_idn,
       pod_idn,
       left(eff_dte, 10)::date as effective_from
  from staging.stg_nm_ocd_podwc__records
 where manifest_id = %(crosswalk_manifest_id)s
"""

_INDEX_CROSSWALK = """
create index on nm_pod_crosswalk (api10, pool_idn, effective_from)
"""

_POD_LATERAL = """
  left join lateral (
       select distinct w.pod_idn as pod_id
         from nm_pod_crosswalk w
        where w.api10 = b.api10
          and w.pool_idn = b.well_completion_pool
          and w.effective_from <= b.effective_from) p on true
"""

# The fan-out and the append in one statement: a completion's PODs are the distinct crosswalk
# entries in force at its effective date, and a completion with none is one row with a null POD.
_APPEND = f"""
insert into {CANONICAL_TABLE} (
    completion_key, api10, api12, well_completion_pool, pool_reported, source_id,
    production_month, report_vintage, source_manifest_id, derivation_id,
    source_operator_key, pod_id, spacing_unit_id, property_id, status_reported,
    status_canonical, effective_from)
select b.completion_key, b.api10, b.api12, b.well_completion_pool, b.pool_reported,
       %(source_id)s, null, %(report_vintage)s, %(manifest_id)s, %(derivation_id)s,
       b.source_operator_key, p.pod_id, b.spacing_unit_id, b.property_id, b.status_reported,
       b.status_canonical, b.effective_from
  from nm_dimension_batch b
{_POD_LATERAL}
 where not exists (
       select 1 from {CANONICAL_TABLE} h
        where h.completion_key = b.completion_key
          and h.source_id = %(source_id)s
          and h.report_vintage = %(report_vintage)s
          and h.effective_from = b.effective_from
          and coalesce(h.pod_id, '') = coalesce(p.pod_id, ''))
"""

_FANOUT = f"""
select count(*) from nm_dimension_batch b
{_POD_LATERAL}
"""

# A same-vintage re-run recomputes an answer or it refuses; it never rewrites one. The compare
# is on the attributes, because the key is what the anti-join in _APPEND already agrees on.
_VINTAGE_DIVERGENCE = f"""
select count(*), min(h.completion_key || ' ' || h.effective_from::text)
  from {CANONICAL_TABLE} h
  join nm_dimension_batch b
    on b.completion_key = h.completion_key and b.effective_from = h.effective_from
 where h.source_id = %(source_id)s
   and h.report_vintage = %(report_vintage)s
   and (h.source_operator_key, h.spacing_unit_id, h.property_id, h.status_reported, h.api10)
       is distinct from
       (b.source_operator_key, b.spacing_unit_id, b.property_id, b.status_reported, b.api10)
"""

_ALIAS_INSERT = f"""
insert into {ALIAS_TABLE} (operator_raw, operator, confidence, effective_from, source_id)
values (%(operator_raw)s, %(operator)s, %(confidence)s, %(effective_from)s, %(source_id)s)
on conflict (operator_raw, effective_from) do nothing
"""


def _staged_frames(
    connection: psycopg.Connection,
    *,
    table: str,
    manifest_id: str,
    batch_rows: int,
) -> Iterator[pl.DataFrame]:
    """The staged rows of one manifest, in ordinal batches, straight out of Postgres.

    Keyset paging on the primary key rather than a server-side cursor: the loop interleaves
    quarantine inserts and a COPY with its own reads, and a portal held open across them is a
    liveness hazard nothing here needs.
    """
    columns = ["source_row_ordinal", *NM_COLUMNS[table]]
    projection = ", ".join(f'"{name}"' for name in columns)
    statement = (
        f"select {projection} from {staging_table_for(table)}"
        " where manifest_id = %(manifest_id)s and source_row_ordinal >= %(after)s"
        " order by source_row_ordinal limit %(limit)s"
    )
    after = 0
    while True:
        with connection.cursor() as cursor:
            cursor.execute(
                statement,
                {"manifest_id": manifest_id, "after": after, "limit": batch_rows},
            )
            rows = cursor.fetchall()
        if not rows:
            return
        yield pl.DataFrame(
            rows, schema={name: pl.String for name in columns}, orient="row"
        ).with_columns(pl.col("source_row_ordinal").cast(pl.Int64))
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


def _route_quarantine(
    run: IngestRun,
    batches: Sequence[QuarantineBatch],
    *,
    stage: str,
    source_id: str,
    staging_table: str,
    manifest_id: str,
    vocabulary: frozenset[str],
    counts: dict[str, int],
) -> None:
    for batch in batches:
        reason = batch.reason_code if batch.reason_code in vocabulary else UNREGISTERED_REASON
        capped = batch.frame.height > QUARANTINE_CAP
        recorded = batch.frame.head(QUARANTINE_CAP) if capped else batch.frame
        result = quarantine(
            run.connection,
            recorded,
            reason_code=reason,
            manifest_id=manifest_id,
            source_id=source_id,
            staging_table=staging_table,
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
                "staging_table": staging_table,
                "reason_code": reason,
                "rule_id": batch.rule_id,
                "rows": batch.frame.height,
                "recorded": recorded.height,
                "opened": result.opened,
                "reoccurred": result.reoccurred,
                "capped": capped,
            },
            correlation_id=run.session.correlation_id,
            occurred_at=run.session.clock.now(),
        )


def completion_records(frame: pl.DataFrame, *, policy: DimensionPolicy) -> pl.DataFrame:
    """The canonical dimension rows one staged batch computes, before the POD fan-out.

    The sentinels are resolved here and nowhere else: '0' and '' mean absent, so they land null
    rather than as an identifier every Validator B group would then be an artefact of.
    """
    absent = list(policy.absent_sentinels)

    def identifier(column: str) -> pl.Expr:
        value = pl.col(column)
        return pl.when(value.is_in(absent) | value.is_null()).then(None).otherwise(value)

    return frame.with_columns(
        # NM ships no wellbore suffix on any in-scope artifact, so the column says absent
        # rather than inferring a bore (cr_nm_wchistory_wellbore_policy_1).
        pl.lit(None, dtype=pl.String).alias("api12"),
        pl.col(policy.pool_column).alias("well_completion_pool"),
        pl.col(policy.pool_column).alias("pool_reported"),
        pl.col(OPERATOR_RAW).alias("source_operator_key"),
        identifier(policy.spacing_unit_field).alias("spacing_unit_id"),
        identifier(policy.property_field).alias("property_id"),
        pl.col(policy.status_field).alias("status_reported"),
        # No codebook maps NM's status letters, so this is an absent mapping and not a mapping
        # to null (cr_nm_wchistory_status_domain_1).
        pl.lit(None, dtype=pl.String).alias("status_canonical"),
        pl.col(policy.effective_from_field)
        .str.slice(0, 10)
        .str.to_date(strict=False)
        .alias(EFFECTIVE_FROM),
    ).select("source_row_ordinal", *DIMENSION_COLUMNS)


def _split_orphans(
    records: pl.DataFrame, *, onsets: pl.DataFrame
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """A completion reaching none of the three identifiers cannot enter a group at all.

    The POD half asks the same question `_POD_LATERAL` asks — is a POD in force *at this
    observation's* effective date — rather than the weaker "was one ever crosswalked". A POD
    exists at date E exactly when the earliest crosswalk date is on or before E, so the onset
    is all the join needs.
    """
    joined = records.join(onsets, on=COMPLETION_KEY, how="left")
    has_pod = pl.col(_ONSET).is_not_null() & (pl.col(_ONSET) <= pl.col(EFFECTIVE_FROM))
    reachable = (
        has_pod | pl.col("spacing_unit_id").is_not_null() | pl.col("property_id").is_not_null()
    ) & pl.col(EFFECTIVE_FROM).is_not_null()
    return (
        joined.filter(reachable).drop(_ONSET),
        joined.filter(~reachable).drop(_ONSET),
    )


def _crosswalk_onsets(connection: psycopg.Connection, *, manifest_id: str) -> pl.DataFrame:
    """The earliest date `podwc` crosswalks each completion to any POD."""
    with connection.cursor() as cursor:
        cursor.execute(
            "select api_st_cde || lpad(api_cnty_cde, 3, '0')"
            "       || lpad(api_well_idn, 5, '0') || ':' || pool_idn as completion_key,"
            "       min(left(eff_dte, 10)::date) as pod_onset"
            "  from staging.stg_nm_ocd_podwc__records where manifest_id = %s"
            " group by 1",
            (manifest_id,),
        )
        rows = cursor.fetchall()
    return pl.DataFrame(
        rows, schema={COMPLETION_KEY: pl.String, _ONSET: pl.Date}, orient="row"
    )


def seed_operator_aliases(
    run: IngestRun,
    *,
    manifest: ManifestRecord,
    rule: ConformanceRule,
    trim: Mapping[str, Any],
) -> tuple[int, int, str]:
    """OGRID → lineage.operator_aliases at confidence 1.000. No fuzzy pass, ever.

    `ogrid_nam` is CHAR(44), so the trim comes off cr_nm_ogrid_pad_1 rather than a .rstrip():
    leading spaces are data elsewhere in NM and the width that makes padding padding is measured
    in the rule row, not here.
    """
    connection = run.connection
    source_id = source_id_for(OPERATOR_TABLE)
    raw_field = str(rule.spec["operator_raw_field"])
    name_field = str(rule.spec["operator_field"])
    confidence = str(rule.spec["confidence"])
    effective_field = str(rule.spec["effective_from_field"])
    declared = trim.get(name_field)
    if declared is None:
        raise RuleSpecError(f"cr_nm_{OPERATOR_TABLE}_pad_1 declares no trim for {name_field}")
    pad_char = str(declared["char"])
    written = 0
    with derive(
        "canonical.promote",
        output=OutputSpec(
            store="postgres",
            dataset=ALIAS_TABLE,
            partition={"source_id": source_id, "manifest_id": manifest.manifest_id},
        ),
        params={"method": str(rule.spec["method"]), "confidence": confidence},
        inputs=[
            InputRef(
                kind="manifest",
                ref_id=manifest.manifest_id,
                role="primary",
                as_of_vintage=manifest.fetch_vintage,
            )
        ],
    ) as aliasing:
        rows = 0
        digests: list[str] = []
        with connection.cursor() as cursor:
            for frame in _staged_frames(
                connection,
                table=OPERATOR_TABLE,
                manifest_id=manifest.manifest_id,
                batch_rows=BATCH_ROWS,
            ):
                rows += frame.height
                aliased = [
                    {
                        "operator_raw": record[raw_field],
                        "operator": (record[name_field] or "").rstrip(pad_char),
                        "confidence": confidence,
                        "effective_from": (record.get(effective_field) or "")[:10]
                        or run.as_of.isoformat(),
                        "source_id": source_id,
                    }
                    for record in frame.iter_rows(named=True)
                ]
                cursor.executemany(_ALIAS_INSERT, aliased)
                written += cursor.rowcount
                digests.append(hash_payload(aliased))
        aliasing.add_rule(rule.rule_id, applied_rows=rows)
        aliasing.set_rows(rows)
        # The registry the batch computed, not the rows the store accepted: a second run inserts
        # nothing and would otherwise hash differently from the run that did the work, which the
        # determinism detector reads as a code change rather than as a repeat.
        aliasing.set_output_hash(hash_payload(sorted(digests)))
    return written, rows, aliasing.derivation_id


def _heads(connection: psycopg.Connection) -> dict[str, ManifestRecord]:
    """The head manifest per source. The three the dimension reads are required; the three
    registries it only counts against are not, and an absent one is reported as zero resolved
    rather than assumed resolved."""
    heads: dict[str, ManifestRecord] = {}
    for table in SOURCE_TABLES:
        try:
            heads[table] = head_manifest(connection, source_id_for(table))
        except LookupError:
            if table not in REGISTRY_TABLES:
                raise
    return heads


def promote_dimensions(
    run: IngestRun,
    *,
    manifests: Mapping[str, ManifestRecord] | None = None,
    batch_rows: int = BATCH_ROWS,
) -> DimensionReport:
    """Promote the completion dimension at the run's vintage, one derivation for the partition."""
    connection = run.connection
    dim_source = source_id_for(DIM_TABLE)
    heads = dict(manifests) if manifests else _heads(connection)
    for table in (DIM_TABLE, CROSSWALK_TABLE, OPERATOR_TABLE):
        _require_columns(connection, table)

    def rules_for(table: str, stage: str) -> list[ConformanceRule]:
        return load_rules(
            connection, source_id=source_id_for(table), stage=stage, as_of=run.as_of
        )

    conform_rules = rules_for(DIM_TABLE, "conform")
    operator_rules = rules_for(OPERATOR_TABLE, "join")
    policy = DimensionPolicy.from_rules([*conform_rules, *operator_rules])
    registry_rule = rule_for_family(operator_rules, REGISTRY_FAMILY)
    pod_rule = rule_for_family(rules_for(CROSSWALK_TABLE, "join"), POD_FAMILY)
    lease_rule = rule_for_family(rules_for(SPINE_TABLE, "join"), LEASE_EQUIVALENT_FAMILY)

    aliases, registered, alias_derivation = seed_operator_aliases(
        run,
        manifest=heads[OPERATOR_TABLE],
        rule=registry_rule,
        trim=rule_for_family(rules_for(OPERATOR_TABLE, "parse"), f"cr_nm_{OPERATOR_TABLE}_pad")
        .spec["trim"],
    )
    connection.commit()
    # Reloaded after the alias write: _alias_join materialises the registry at load time, so a
    # rule read before the rows existed would join against an empty table.
    alias_rule = rule_for_family(rules_for(OPERATOR_TABLE, "join"), OPERATOR_FAMILY)

    vocabulary = _reason_vocabulary(connection)
    onsets = _crosswalk_onsets(connection, manifest_id=heads[CROSSWALK_TABLE].manifest_id)
    counts: dict[str, int] = {}
    staged_rows = 0
    kept = 0
    stamped: dict[str, int] = {}

    with derive(
        "canonical.promote",
        output=OutputSpec(
            store="postgres",
            dataset=CANONICAL_TABLE,
            partition={"source_id": dim_source, "report_vintage": run.as_of.isoformat()},
        ),
        params={
            "wellbore_policy": policy.wellbore_status,
            "absent_sentinels": list(policy.absent_sentinels),
            "pod_effective_predicate": str(pod_rule.spec["effective_predicate"]),
            "grouping_key": list(lease_rule.spec["grouping_key"]),
        },
        inputs=[
            InputRef(
                kind="manifest",
                ref_id=heads[table].manifest_id,
                role="primary" if table == DIM_TABLE else "crosswalk",
                as_of_vintage=heads[table].fetch_vintage,
            )
            for table in SOURCE_TABLES
            if table in heads
        ],
    ) as promotion:
        with connection.cursor() as cursor:
            cursor.execute(_CREATE_BATCH)
            cursor.execute(
                _CREATE_CROSSWALK,
                {"crosswalk_manifest_id": heads[CROSSWALK_TABLE].manifest_id},
            )
            cursor.execute(_INDEX_CROSSWALK)
            cursor.execute("analyze nm_pod_crosswalk")
        digests: list[str] = []
        for frame in _staged_frames(
            connection,
            table=DIM_TABLE,
            manifest_id=heads[DIM_TABLE].manifest_id,
            batch_rows=batch_rows,
        ):
            staged_rows += frame.height
            conformed = apply_rules(frame, conform_rules)
            _route_batches(
                run, conformed.quarantined, stage="conform", vocabulary=vocabulary, counts=counts,
                manifest_id=heads[DIM_TABLE].manifest_id,
            )
            aliased = apply_rules(
                conformed.frame.rename({policy.operator_column: OPERATOR_RAW}), [alias_rule]
            )
            _route_batches(
                run, aliased.quarantined, stage="join", vocabulary=vocabulary, counts=counts,
                manifest_id=heads[DIM_TABLE].manifest_id,
            )
            records = completion_records(aliased.frame, policy=policy)
            landable, orphans = _split_orphans(records, onsets=onsets)
            if not orphans.is_empty():
                _route_batches(
                    run,
                    [
                        QuarantineBatch(
                            reason_code=policy.orphan_reason,
                            rule_id=policy.cite(IDENTIFIER_FAMILY),
                            frame=orphans,
                        )
                    ],
                    stage="join",
                    vocabulary=vocabulary,
                    counts=counts,
                    manifest_id=heads[DIM_TABLE].manifest_id,
                )
            kept += landable.height
            digests.append(hash_payload(landable.drop("source_row_ordinal").rows()))
            _load_batch(connection, landable)
            for application in (conformed, aliased):
                for rule_id in application.applied_rule_ids:
                    stamped[rule_id] = (
                        stamped.get(rule_id, 0) + application.applied_rows[rule_id]
                    )

        parameters = {
            "source_id": dim_source,
            "report_vintage": run.as_of,
            "manifest_id": heads[DIM_TABLE].manifest_id,
            "derivation_id": None,
            "crosswalk_manifest_id": heads[CROSSWALK_TABLE].manifest_id,
        }
        with connection.cursor() as cursor:
            cursor.execute("analyze nm_dimension_batch")
        _refuse_vintage_rewrite(connection, parameters)
        fanout = _scalar(connection, _FANOUT, parameters)
        # The three declarations judged every observation and stamp no count of their own.
        for family in (EFFECTIVE_FAMILY, WELLBORE_FAMILY, STATUS_FAMILY, IDENTIFIER_FAMILY):
            stamped[policy.cite(family)] = staged_rows
        stamped[pod_rule.rule_id] = fanout
        stamped[lease_rule.rule_id] = kept
        stamped[registry_rule.rule_id] = registered
        for rule_id, rows in stamped.items():
            promotion.add_rule(rule_id, applied_rows=rows)
        promotion.set_rows(kept)
        # What the batch computed, not what the store kept: hashing the appended subset would
        # make the derivation a function of prior state (nm_ocd.py's precedent).
        promotion.set_output_hash(hash_payload(sorted(digests)))

    # The derivation_id is a content address the block only assigns on the way out, and the
    # canonical row references it, so the append is the first thing after it.
    promoted = _append(connection, {**parameters, "derivation_id": promotion.derivation_id})
    resolution = _registry_resolution(connection, heads)
    rejected = sum(counts.values())
    if staged_rows != kept + rejected:
        raise RowCountMismatch(
            f"{CANONICAL_TABLE}: read {staged_rows} observations but kept {kept} and quarantined"
            f" {rejected}; an observation that was read is exactly one of those (SB-01 §5.1)"
        )
    report = DimensionReport(
        source_id=dim_source,
        report_vintage=run.as_of,
        manifest_ids={table: head.manifest_id for table, head in heads.items()},
        staged_rows=staged_rows,
        kept_completions=kept,
        promoted_rows=promoted,
        aliases_written=aliases,
        aliases_registered=registered,
        pod_fanout=fanout,
        wellbore_policy=policy.wellbore_status,
        quarantined=counts,
        resolution=resolution,
        derivation_id=promotion.derivation_id,
        alias_derivation_id=alias_derivation,
    )
    return _close_vintage(run, report)


def _route_batches(
    run: IngestRun,
    batches: Sequence[QuarantineBatch],
    *,
    stage: str,
    vocabulary: frozenset[str],
    counts: dict[str, int],
    manifest_id: str,
) -> None:
    _route_quarantine(
        run,
        batches,
        stage=stage,
        source_id=source_id_for(DIM_TABLE),
        staging_table=staging_table_for(DIM_TABLE),
        manifest_id=manifest_id,
        vocabulary=vocabulary,
        counts=counts,
    )


def _load_batch(connection: psycopg.Connection, records: pl.DataFrame) -> None:
    columns = ", ".join(f'"{name}"' for name in DIMENSION_COLUMNS)
    with (
        connection.cursor() as cursor,
        cursor.copy(f"copy nm_dimension_batch ({columns}) from stdin") as copy,
    ):
        for row in records.select(DIMENSION_COLUMNS).iter_rows():
            copy.write_row(row)


def _scalar(connection: psycopg.Connection, statement: str, parameters: Mapping[str, Any]) -> int:
    with connection.cursor() as cursor:
        cursor.execute(statement, dict(parameters))
        row = cursor.fetchone()
    return int(row[0]) if row else 0


def _append(connection: psycopg.Connection, parameters: Mapping[str, Any]) -> int:
    with connection.cursor() as cursor:
        cursor.execute(_APPEND, dict(parameters))
        return cursor.rowcount


def _refuse_vintage_rewrite(
    connection: psycopg.Connection, parameters: Mapping[str, Any]
) -> None:
    with connection.cursor() as cursor:
        cursor.execute(_VINTAGE_DIVERGENCE, dict(parameters))
        rows, example = cursor.fetchone()
    if rows:
        raise VintageAlreadyPromoted(
            CANONICAL_TABLE, parameters["report_vintage"], int(rows), example
        )


def _registry_resolution(
    connection: psycopg.Connection, heads: Mapping[str, ManifestRecord]
) -> dict[str, int]:
    """How many promoted identifiers a registry has a row for. Reported, never required."""
    statements = {
        "pod": (
            "select count(*) from (select distinct c.pod_id from canonical.well_completions c"
            "  join staging.stg_nm_ocd_pod__records r on r.pod_idn = c.pod_id"
            " where c.source_id = %(source_id)s and r.manifest_id = %(manifest_id)s) t"
        ),
        "spacingunit": (
            "select count(*) from (select distinct c.spacing_unit_id"
            "   from canonical.well_completions c"
            "   join staging.stg_nm_ocd_spacingunit__records r"
            "     on r.spc_unit_idn = c.spacing_unit_id"
            "  where c.source_id = %(source_id)s and r.manifest_id = %(manifest_id)s) t"
        ),
        "property": (
            "select count(*) from (select distinct c.property_id"
            "   from canonical.well_completions c"
            "   join staging.stg_nm_ocd_property__records r"
            "     on r.prod_prop_idn = c.property_id"
            "  where c.source_id = %(source_id)s and r.manifest_id = %(manifest_id)s) t"
        ),
    }
    source_id = source_id_for(DIM_TABLE)
    return {
        registry: (
            0
            if registry not in heads
            else _scalar(
                connection,
                statement,
                {"source_id": source_id, "manifest_id": heads[registry].manifest_id},
            )
        )
        for registry, statement in statements.items()
    }


def _reason_vocabulary(connection: psycopg.Connection) -> frozenset[str]:
    from glasswell.ingest.nm_ocd import _reason_vocabulary as vocabulary

    return vocabulary(connection)


def _close_vintage(run: IngestRun, report: DimensionReport) -> DimensionReport:
    """One ledger row per (source, day): same-day passes accumulate onto it (DR-85), and a
    re-run that appended nothing leaves the pass that did the work alone (gate-nm-fp D2)."""
    connection = run.connection
    record = record_vintage_day(
        connection,
        source_id=report.source_id,
        vintage_date=report.report_vintage,
        manifest_ids=sorted(set(report.manifest_ids.values())),
        opened_at=run.session.clock.now(),
        promotion_derivation_id=report.derivation_id,
        rows_examined=report.staged_rows,
        rows_appended=report.promoted_rows,
    )
    if record is None:
        return report
    emit(
        connection,
        "canonical.promotion_completed",
        subject_type="vintage",
        subject_id=record.vintage_id,
        payload=report.to_dict(),
        correlation_id=run.session.correlation_id,
        occurred_at=run.session.clock.now(),
    )
    return DimensionReport(
        source_id=report.source_id,
        report_vintage=report.report_vintage,
        manifest_ids=report.manifest_ids,
        staged_rows=report.staged_rows,
        kept_completions=report.kept_completions,
        promoted_rows=report.promoted_rows,
        aliases_written=report.aliases_written,
        aliases_registered=report.aliases_registered,
        pod_fanout=report.pod_fanout,
        wellbore_policy=report.wellbore_policy,
        quarantined=report.quarantined,
        resolution=report.resolution,
        derivation_id=report.derivation_id,
        alias_derivation_id=report.alias_derivation_id,
        vintage_id=record.vintage_id,
    )


def run_dimensions(
    connection: psycopg.Connection,
    *,
    batch_rows: int = BATCH_ROWS,
    env_id: str | None = None,
    code_version: str | None = None,
) -> DimensionReport:
    resolved = resolve_environment(connection, env_id=env_id, code_version=code_version)
    with open_ingest_run(
        connection, source_id=source_id_for(DIM_TABLE), environment=resolved
    ) as run:
        return promote_dimensions(run, batch_rows=batch_rows)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Promote the NM completion dimension from the staged sibling tables."
    )
    add_dsn_argument(parser)
    parser.add_argument("--batch-rows", type=int, default=BATCH_ROWS)
    parser.add_argument("--env-id", default=None)
    parser.add_argument("--code-version", default=None)
    arguments = parser.parse_args(argv)
    arguments.dsn = resolve_dsn(arguments.dsn)

    connection = psycopg.connect(arguments.dsn)
    try:
        try:
            report = run_dimensions(
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
