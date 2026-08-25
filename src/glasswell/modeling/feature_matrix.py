"""As-of feature materialization into a D1, content-addressed Parquet partition."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import polars as pl
import psycopg
from psycopg.rows import dict_row

from glasswell.ingest.base import resolve_environment
from glasswell.lineage.as_of import AsOfViolation, read_feature_snapshot
from glasswell.lineage.capture import derive, lineage_session
from glasswell.lineage.clock import Clock
from glasswell.lineage.ids import derivation_id
from glasswell.lineage.models import DeriveEnvironment, InputRef, OutputSpec
from glasswell.lineage.recipes import build_recipe
from glasswell.lineage.store import PostgresRecorder
from glasswell.modeling.features import (
    FeatureEvents,
    FeatureObservation,
    FeatureSpec,
    active_feature_specs,
    feature_set_hash,
    observe_feature,
)
from glasswell.staging.duck import PARTITION_FILENAME, file_sha256, write_partition

FEATURE_ROOT_ENV = "GLASSWELL_FEATURE_ROOT"
DEFAULT_FEATURE_ROOT = Path("data/features")
FEATURE_DATASET = "features.well_features"
FEATURE_SCHEMA_VERSION = "1"
DEFAULT_FEATURE_VERSION = "fv1.0"
DEFAULT_FEATURE_SET = "full"
DEFAULT_STATE_CODE = "33"
DEFAULT_BASIN = "williston"


class FeatureMatrixError(RuntimeError):
    """Base class for matrix build failures."""


class EmptyFeatureMatrixError(FeatureMatrixError):
    """No subject has the completion-date anchor required by the pre-production regime."""


class UnsupportedFeatureSpecError(FeatureMatrixError):
    """The registry requested semantics this materializer does not implement."""


class ConflictingFeatureValueError(FeatureMatrixError):
    """A well resolves to more than one value for a single-valued feature."""


class ImmutableFeaturePartitionError(FeatureMatrixError):
    """An existing version/vintage partition has different bytes."""


@dataclass(frozen=True, slots=True)
class FeatureMatrixBuild:
    derivation_id: str
    recipe_id: str
    feature_version: str
    feature_set_hash: str
    as_of_vintage: date
    artifact_uri: str
    artifact_sha256: str
    rows: int
    columns: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "derivation_id": self.derivation_id,
            "recipe_id": self.recipe_id,
            "feature_version": self.feature_version,
            "feature_set_hash": self.feature_set_hash,
            "as_of_vintage": self.as_of_vintage.isoformat(),
            "artifact_uri": self.artifact_uri,
            "artifact_sha256": self.artifact_sha256,
            "rows": self.rows,
            "columns": list(self.columns),
        }


@dataclass(frozen=True, slots=True)
class _FeaturePlan:
    specs: tuple[FeatureSpec, ...]
    observations: tuple[tuple[str, date, tuple[FeatureObservation, ...]], ...]
    inputs: tuple[InputRef, ...]
    params: Mapping[str, object]
    feature_set_hash: str


def resolve_feature_root(explicit: Path | str | None = None) -> Path:
    if explicit is not None:
        return Path(explicit)
    return Path(os.environ.get(FEATURE_ROOT_ENV) or DEFAULT_FEATURE_ROOT)


def load_feature_specs(connection: psycopg.Connection) -> tuple[FeatureSpec, ...]:
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            "select feature_id, family, dtype, unit, knowable_at_rule,"
            " publication_lag_days_p50, transform_id, params, source_refs, missing_policy,"
            " member_of, introduced_in_fv, retired_in_fv"
            " from features.feature_specs order by feature_id, introduced_in_fv"
        )
        return tuple(FeatureSpec(**row) for row in cursor.fetchall())


def build_feature_matrix(
    connection: psycopg.Connection,
    *,
    as_of: date,
    environment: DeriveEnvironment,
    feature_version: str = DEFAULT_FEATURE_VERSION,
    set_name: str = DEFAULT_FEATURE_SET,
    root: Path | str | None = None,
    clock: Clock | None = None,
) -> FeatureMatrixBuild:
    """Build one immutable `(feature_version, as_of_vintage)` feature partition."""
    plan = _prepare_plan(
        connection,
        as_of=as_of,
        feature_version=feature_version,
        set_name=set_name,
    )
    partition = {"feature_version": feature_version, "as_of_vintage": as_of.isoformat()}
    planned_output = OutputSpec(
        store="parquet",
        dataset=FEATURE_DATASET,
        partition=partition,
        schema_version=FEATURE_SCHEMA_VERSION,
    )
    planned_id = derivation_id(
        operation="features.build",
        inputs=plan.inputs,
        params=plan.params,
        code_version=environment.code_version,
        env_id=environment.env_id,
        rule_ids=(),
        output=planned_output,
    )
    frame = _matrix_frame(plan, planned_id, feature_version, as_of)
    artifact_uri, artifact_sha256 = _persist_frame(
        frame,
        root=resolve_feature_root(root),
        feature_version=feature_version,
        as_of=as_of,
    )
    lockfile_sha256 = _lockfile_sha256(connection, environment.env_id)
    recipe_id = build_recipe(
        connection,
        "features.build",
        code_version=environment.code_version,
        lockfile_sha256=lockfile_sha256,
        entry_point="glasswell.modeling.feature_matrix:build_feature_matrix",
        params=plan.params,
        input_refs=plan.inputs,
        determinism_class="D1",
        output={
            "dataset": FEATURE_DATASET,
            "partition": partition,
            "sha256": artifact_sha256,
            "rows": frame.height,
            "schema_version": FEATURE_SCHEMA_VERSION,
            "determinism_class": "D1",
        },
    )
    resolved_environment = environment.model_copy(update={"recipe_id": recipe_id})
    output = planned_output.model_copy(update={"locator": artifact_uri})
    with lineage_session(
        recorder=PostgresRecorder(connection), environment=resolved_environment, clock=clock
    ), derive(
        "features.build",
        output=output,
        params=plan.params,
        inputs=plan.inputs,
        determinism_class="D1",
        ttl_class="permanent",
    ) as context:
        context.set_output_hash(artifact_sha256)
        context.set_rows(frame.height)
    if context.derivation_id != planned_id:
        raise FeatureMatrixError(
            f"planned derivation {planned_id} became {context.derivation_id} during capture"
        )
    return FeatureMatrixBuild(
        derivation_id=context.derivation_id,
        recipe_id=recipe_id,
        feature_version=feature_version,
        feature_set_hash=plan.feature_set_hash,
        as_of_vintage=as_of,
        artifact_uri=artifact_uri,
        artifact_sha256=artifact_sha256,
        rows=frame.height,
        columns=tuple(frame.columns),
    )


def _prepare_plan(
    connection: psycopg.Connection,
    *,
    as_of: date,
    feature_version: str,
    set_name: str,
) -> _FeaturePlan:
    if set_name != DEFAULT_FEATURE_SET:
        raise UnsupportedFeatureSpecError(
            "the persisted well_features partition is the full set; named subsets are consumers"
        )
    all_specs = load_feature_specs(connection)
    specs = active_feature_specs(all_specs, set_name=set_name, feature_version=feature_version)
    _validate_specs(specs)
    set_hash = feature_set_hash(all_specs, set_name=set_name, feature_version=feature_version)
    min_confidence = _formation_min_confidence(specs)
    formation_source_id = _formation_source_id(specs)
    try:
        snapshot = read_feature_snapshot(
            connection,
            as_of=as_of,
            state_code=DEFAULT_STATE_CODE,
            basin=DEFAULT_BASIN,
            min_confidence=min_confidence,
            formation_source_id=formation_source_id,
        )
    except AsOfViolation as error:
        raise FeatureMatrixError(str(error)) from error
    if not snapshot.rows:
        raise EmptyFeatureMatrixError(
            f"no {DEFAULT_STATE_CODE}/{DEFAULT_BASIN} wells have a completion_date anchor"
            f" at {as_of}"
        )
    inputs = _feature_inputs(snapshot.inputs, set_hash=set_hash)
    observations = tuple(_observe_row(row, specs) for row in snapshot.rows)
    if not any(
        observation.value is not None
        for _, _, subject_observations in observations
        for observation in subject_observations
    ):
        raise EmptyFeatureMatrixError(
            "no registered feature value resolves for"
            f" {DEFAULT_STATE_CODE}/{DEFAULT_BASIN} at {as_of}"
        )
    params: dict[str, object] = {
        "as_of_vintage": as_of.isoformat(),
        "feature_version": feature_version,
        "feature_set": set_name,
        "feature_set_hash": set_hash,
        "state_code": DEFAULT_STATE_CODE,
        "basin": DEFAULT_BASIN,
        "anchor": "completion_date",
        "sort_order": ["api10"],
        "parquet": {"compression": "zstd", "compression_level": 3},
    }
    return _FeaturePlan(
        specs=specs,
        observations=observations,
        inputs=inputs,
        params=params,
        feature_set_hash=set_hash,
    )


def _validate_specs(specs: Sequence[FeatureSpec]) -> None:
    for spec in specs:
        if spec.transform_id != "lookup_formation_alias":
            raise UnsupportedFeatureSpecError(
                f"{spec.feature_id} uses unsupported transform {spec.transform_id!r}"
            )
        if spec.missing_policy != "native_nan":
            raise UnsupportedFeatureSpecError(
                f"{spec.feature_id} uses unsupported missing policy {spec.missing_policy!r}"
            )
        if spec.dtype != "categorical":
            raise UnsupportedFeatureSpecError(
                f"{spec.feature_id} uses unsupported dtype {spec.dtype!r}"
            )


def _formation_min_confidence(specs: Sequence[FeatureSpec]) -> Decimal:
    values = {str(spec.params.get("min_confidence")) for spec in specs}
    if len(values) != 1:
        raise UnsupportedFeatureSpecError("formation alias transforms disagree on min_confidence")
    aliases = {spec.params.get("alias_table") for spec in specs}
    fields = {spec.params.get("reported_pool_field") for spec in specs}
    if aliases != {"lineage.formation_aliases"} or fields != {"pool_reported"}:
        raise UnsupportedFeatureSpecError("formation alias transform parameters are not supported")
    return Decimal(values.pop())


def _formation_source_id(specs: Sequence[FeatureSpec]) -> str:
    values = {spec.params.get("source_id") for spec in specs}
    if values != {"nd_mpr_xlsx"}:
        raise UnsupportedFeatureSpecError("formation alias source is not supported")
    return "nd_mpr_xlsx"


def _feature_inputs(inputs: Sequence[InputRef], *, set_hash: str) -> tuple[InputRef, ...]:
    refs = [
        *inputs,
        InputRef(
            kind="external",
            ref_id=f"features.feature_specs:{set_hash}",
            role="validator",
        ),
    ]
    return tuple(ref.model_copy(update={"ord": ordinal}) for ordinal, ref in enumerate(refs))


def _observe_row(
    row: Mapping[str, object], specs: Sequence[FeatureSpec]
) -> tuple[str, date, tuple[FeatureObservation, ...]]:
    api10 = str(row["api10"])
    anchor = row["completion_date"]
    if not isinstance(anchor, date):
        raise FeatureMatrixError(f"{api10} has no completion_date anchor")
    formations = tuple(row["formations"] or ())
    if len(formations) > 1:
        raise ConflictingFeatureValueError(
            f"geology.formation_group for {api10} resolves to {formations!r}"
        )
    value = formations[0] if formations else None
    events = FeatureEvents(
        spud_date=row["spud_date"] if isinstance(row["spud_date"], date) else None,
        completion_date=anchor,
        anchor=anchor,
    )
    observations = tuple(
        observe_feature(api10=api10, spec=spec, value=value, events=events) for spec in specs
    )
    return api10, anchor, observations


def _matrix_frame(
    plan: _FeaturePlan, derivation: str, feature_version: str, as_of: date
) -> pl.DataFrame:
    schema: dict[str, pl.DataType] = {
        "api10": pl.String,
        "feature_version": pl.String,
        "feature_set_hash": pl.String,
        "as_of_vintage": pl.Date,
        "anchor": pl.Date,
        "derivation_id": pl.String,
    }
    for spec in plan.specs:
        schema[spec.feature_id] = pl.String
        schema[f"{spec.feature_id}__knowable_at"] = pl.Date
    rows = []
    for api10, anchor, observations in plan.observations:
        output: dict[str, object] = {
            "api10": api10,
            "feature_version": feature_version,
            "feature_set_hash": plan.feature_set_hash,
            "as_of_vintage": as_of,
            "anchor": anchor,
            "derivation_id": derivation,
        }
        for observation in observations:
            output[observation.feature_id] = observation.value
            output[f"{observation.feature_id}__knowable_at"] = observation.knowable_at
        rows.append(output)
    return pl.DataFrame(rows, schema=schema, orient="row")


def _persist_frame(
    frame: pl.DataFrame, *, root: Path, feature_version: str, as_of: date
) -> tuple[str, str]:
    partition = (
        root
        / "well_features"
        / f"feature_version={feature_version}"
        / f"as_of_vintage={as_of.isoformat()}"
    )
    partition.mkdir(parents=True, exist_ok=True)
    pending = partition / f".pending-{uuid4().hex}.parquet"
    try:
        written = write_partition([frame], pending, sort_order="api10")
        digest = written.sha256
        final = partition / f"sha256={digest}" / PARTITION_FILENAME
        existing = sorted(partition.glob(f"sha256=*/{PARTITION_FILENAME}"))
        conflicts = [path for path in existing if path != final]
        if conflicts:
            raise ImmutableFeaturePartitionError(
                f"{feature_version}/{as_of} already resolves to {conflicts[0].parent.name}"
            )
        final.parent.mkdir(parents=True, exist_ok=True)
        if final.exists():
            if file_sha256(final) != digest:
                raise ImmutableFeaturePartitionError(f"stored artifact {final} failed its address")
            pending.unlink()
        else:
            os.replace(pending, final)
        return str(final), digest
    finally:
        pending.unlink(missing_ok=True)


def _lockfile_sha256(connection: psycopg.Connection, env_id: str) -> str | None:
    with connection.cursor() as cursor:
        cursor.execute(
            "select lockfile_sha256 from lineage.environments where env_id = %s", (env_id,)
        )
        row = cursor.fetchone()
    if row is None:
        raise FeatureMatrixError(f"environment {env_id!r} is not registered")
    return row[0]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a pinned feature matrix partition.")
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--as-of", required=True, help="knowledge-time cut, YYYY-MM-DD")
    parser.add_argument("--feature-version", default=DEFAULT_FEATURE_VERSION)
    parser.add_argument("--feature-set", default=DEFAULT_FEATURE_SET)
    parser.add_argument("--root", default=None)
    parser.add_argument("--env-id", default=None)
    parser.add_argument("--code-version", default=None)
    arguments = parser.parse_args(argv)
    with psycopg.connect(arguments.dsn) as connection:
        environment = resolve_environment(
            connection, env_id=arguments.env_id, code_version=arguments.code_version
        )
        report = build_feature_matrix(
            connection,
            as_of=date.fromisoformat(arguments.as_of),
            environment=environment,
            feature_version=arguments.feature_version,
            set_name=arguments.feature_set,
            root=arguments.root,
        )
        connection.commit()
    print(json.dumps(report.to_dict(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
