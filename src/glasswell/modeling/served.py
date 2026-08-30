"""Resolve the one control artifact a served figure may read, and read only that one.

Nothing here imports the serving layer: the resolver refuses with `UnregisteredArtifact` and
the routers translate that into their own problem code. Inverting the dependency would put the
API layer inside `modeling`.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

import polars as pl
import psycopg

from glasswell.modeling.model_dataset import resolve_model_root
from glasswell.modeling.type_curve import CONTROL_DATASET
from glasswell.staging.duck import file_sha256

PUBLICATION_DATASET = "api.modeling_publication"
TYPE_CURVE_DATASET = "api.type_curve"
TYPE_CURVE_INDEX_DATASET = "api.type_curve_index"

SERVED_COLUMNS: tuple[str, ...] = (
    "subject_api10",
    "split_id",
    "split_sha256",
    "origin",
    "knowledge_cutoff",
    "eval_vintage",
    "horizon_months",
    "month_index",
    "stream",
    "unit",
    "normalization",
    "fallback_level",
    "control_unavailable_reasons",
    "peer_set_id",
    "peer_count",
    "cumulative_peer_count",
    "status",
    "cumulative_status",
    "monthly_p10",
    "monthly_p50",
    "monthly_p90",
    "cumulative_p10",
    "cumulative_p50",
    "cumulative_p90",
    "quantile_convention",
    "formation_group",
    "area",
    "lateral_length_bucket",
    "subject_lateral_length_ft",
)

_DIGEST_CACHE_LIMIT = 8
_digest_cache: dict[tuple[str, tuple[int, int, int, int]], str] = {}
_coverage_cache: dict[tuple[str, tuple[int, int, int, int]], Mapping[str, Any]] = {}


class UnregisteredArtifact(RuntimeError):
    """A served figure would have to come from bytes no accepted publication names."""


@dataclass(frozen=True, slots=True)
class PinnedControl:
    publication_id: str
    receipt: Mapping[str, Any]
    superseded: tuple[str, ...]
    control_derivation_id: str
    model_dataset_derivation_id: str
    feature_derivation_id: str
    artifact_path: Path
    artifact_sha256: str
    coverage_path: Path
    rows: int
    control_version: str
    dataset_version: str
    feature_version: str
    split_set_id: str
    eval_vintage: date
    basin: str
    vintage_basis: str
    code_version: str
    environment_id: str


def accepted_publications(
    connection: psycopg.Connection, *, basin: str | None = None
) -> tuple[Mapping[str, Any], ...]:
    """Every accepted receipt, newest evaluation vintage first, ties broken by id."""
    clause = " where basin = %s" if basin else ""
    parameters: tuple[Any, ...] = (basin,) if basin else ()
    with connection.cursor() as cursor:
        cursor.execute(
            "select publication_id, document, basin, eval_vintage, vintage_basis,"
            "       feature_version, model_dataset_version, control_version, split_set_id,"
            "       code_version, environment_id, feature_derivation_id,"
            "       model_dataset_derivation_id, control_derivation_id, created_at"
            " from lineage.p3_publication_receipts" + clause + " order by eval_vintage desc,"
            " publication_id desc",
            parameters,
        )
        columns = [description[0] for description in cursor.description]
        return tuple(dict(zip(columns, row, strict=True)) for row in cursor.fetchall())


def resolve_pinned_control(
    connection: psycopg.Connection, *, publication_id: str | None = None
) -> PinnedControl:
    """Refuse unless an accepted publication, a registered derivation, the two records and
    the bytes on disk all name the same artifact."""
    receipts = accepted_publications(connection)
    if not receipts:
        raise UnregisteredArtifact(
            "no accepted P3 publication receipt names a servable type-curve control"
        )
    if publication_id is None:
        receipt = receipts[0]
    else:
        receipt = next(
            (item for item in receipts if item["publication_id"] == publication_id), None
        )
        if receipt is None:
            raise UnregisteredArtifact(
                f"publication {publication_id} is not an accepted P3 publication"
            )
    superseded = tuple(
        item["publication_id"]
        for item in receipts
        if item["basin"] == receipt["basin"] and item["publication_id"] != receipt["publication_id"]
    )

    derivation = _registered_control(connection, str(receipt["control_derivation_id"]))
    document = _document(receipt)
    locator = _document_text(document, "artifact_uri", "type_curve")
    digest = _document_text(document, "artifact_sha256", "type_curve")
    if locator != derivation["output_locator"]:
        raise UnregisteredArtifact(
            f"receipt {receipt['publication_id']} names {locator!r} but derivation"
            f" {derivation['derivation_id']} was registered against"
            f" {derivation['output_locator']!r}"
        )
    if digest != derivation["output_sha256"]:
        raise UnregisteredArtifact(
            f"receipt {receipt['publication_id']} names artifact digest {digest} but derivation"
            f" {derivation['derivation_id']} recorded {derivation['output_sha256']}"
        )

    artifact_path = _contained_regular_file(locator)
    if _digest_of(artifact_path) != digest:
        raise UnregisteredArtifact(
            f"{artifact_path} does not hash to the registered digest {digest}"
        )
    coverage_locator = _document_text(document, "artifact_uri", "type_curve_coverage")
    rows = document.get("rows")
    return PinnedControl(
        publication_id=str(receipt["publication_id"]),
        receipt=document,
        superseded=superseded,
        control_derivation_id=str(receipt["control_derivation_id"]),
        model_dataset_derivation_id=str(receipt["model_dataset_derivation_id"]),
        feature_derivation_id=str(receipt["feature_derivation_id"]),
        artifact_path=artifact_path,
        artifact_sha256=digest,
        coverage_path=Path(coverage_locator),
        rows=int(rows["type_curve"]) if isinstance(rows, Mapping) else 0,
        control_version=str(receipt["control_version"]),
        dataset_version=str(receipt["model_dataset_version"]),
        feature_version=str(receipt["feature_version"]),
        split_set_id=str(receipt["split_set_id"]),
        eval_vintage=receipt["eval_vintage"],
        basin=str(receipt["basin"]),
        vintage_basis=str(receipt["vintage_basis"]),
        code_version=str(receipt["code_version"]),
        environment_id=str(receipt["environment_id"]),
    )


def control_coverage(pin: PinnedControl) -> Mapping[str, Any]:
    """The sibling coverage document, digest-checked against the receipt before it is parsed."""
    expected = _document_text(pin.receipt, "artifact_sha256", "type_curve_coverage")
    path = _contained_regular_file(str(pin.coverage_path))
    key = (str(path), _stat_tuple(path))
    cached = _coverage_cache.get(key)
    if cached is not None:
        return cached
    if file_sha256(path) != expected:
        raise UnregisteredArtifact(
            f"{path} does not hash to the digest the receipt registered for it"
        )
    payload = json.loads(path.read_bytes())
    if not isinstance(payload, Mapping):
        raise UnregisteredArtifact(f"{path} is not a JSON object")
    _remember(_coverage_cache, key, payload)
    return payload


def subject_frame(
    pin: PinnedControl,
    *,
    api10: str,
    stream: str,
    normalization: str,
    origin: date | None,
    horizon_months: int,
) -> pl.DataFrame:
    """The month-indexed curve for one subject instance; empty when the subject has no rows."""
    predicate = (
        (pl.col("subject_api10") == api10)
        & (pl.col("stream") == stream)
        & (pl.col("normalization") == normalization)
        & (pl.col("horizon_months") == horizon_months)
    )
    if origin is not None:
        predicate = predicate & (pl.col("origin") == origin)
    return _collect(
        pin,
        pl.scan_parquet(pin.artifact_path)
        .filter(predicate)
        .select(SERVED_COLUMNS)
        .sort(["origin", "month_index"]),
    )


def subject_origins(pin: PinnedControl, *, api10: str) -> tuple[tuple[date, int, str], ...]:
    """The (origin, horizon, split) instances the control holds for one subject."""
    frame = _collect(
        pin,
        pl.scan_parquet(pin.artifact_path)
        .filter(pl.col("subject_api10") == api10)
        .select(["origin", "horizon_months", "split_id"])
        .unique()
        .sort(["origin", "horizon_months"]),
    )
    return tuple(
        (row[0], int(row[1]), str(row[2])) for row in frame.iter_rows()
    )


def index_page(
    pin: PinnedControl,
    *,
    stream: str,
    normalization: str,
    horizon_months: int,
    origin: date | None,
    fallback_level: str | None,
    formation_group: str | None,
    after_api10: str | None,
    limit: int,
) -> pl.DataFrame:
    """One page of subject instances at the horizon row, plus one row of lookahead."""
    predicate = (
        (pl.col("stream") == stream)
        & (pl.col("normalization") == normalization)
        & (pl.col("horizon_months") == horizon_months)
        & (pl.col("month_index") == horizon_months)
    )
    if origin is not None:
        predicate = predicate & (pl.col("origin") == origin)
    if fallback_level is not None:
        predicate = predicate & (pl.col("fallback_level") == fallback_level)
    if formation_group is not None:
        predicate = predicate & (pl.col("formation_group") == formation_group)
    if after_api10 is not None:
        predicate = predicate & (pl.col("subject_api10") > after_api10)
    return _collect(
        pin,
        pl.scan_parquet(pin.artifact_path)
        .filter(predicate)
        .select(SERVED_COLUMNS)
        .sort(["subject_api10", "origin"])
        .head(limit + 1),
    )


def decimal_text(value: float | int | None, places: str = "0.01") -> str | None:
    """Round once, at the serving edge, half up."""
    if value is None:
        return None
    return str(Decimal(str(value)).quantize(Decimal(places), rounding=ROUND_HALF_UP))


def _registered_control(connection: psycopg.Connection, derivation_id: str) -> Mapping[str, Any]:
    with connection.cursor() as cursor:
        cursor.execute(
            "select derivation_id, operation, output_store, output_dataset, output_locator,"
            "       output_sha256, status, output_partition"
            " from lineage.derivations where derivation_id = %s",
            (derivation_id,),
        )
        row = cursor.fetchone()
        columns = [description[0] for description in cursor.description]
    if row is None:
        raise UnregisteredArtifact(
            f"the accepted publication names control derivation {derivation_id}, which is not"
            " registered in lineage.derivations"
        )
    record = dict(zip(columns, row, strict=True))
    expected = {
        "operation": "typecurve.build",
        "output_store": "parquet",
        "output_dataset": CONTROL_DATASET,
        "status": "ok",
    }
    for column, value in expected.items():
        if record[column] != value:
            raise UnregisteredArtifact(
                f"control derivation {derivation_id} has {column}={record[column]!r}, not"
                f" {value!r}"
            )
    if not record["output_locator"] or not record["output_sha256"]:
        raise UnregisteredArtifact(
            f"control derivation {derivation_id} was registered without a locator and digest"
        )
    return record


def _document(receipt: Mapping[str, Any]) -> Mapping[str, Any]:
    document = receipt["document"]
    if not isinstance(document, Mapping):
        raise UnregisteredArtifact(
            f"receipt {receipt['publication_id']} does not carry a JSON object"
        )
    return document


def _document_text(document: Mapping[str, Any], section: str, key: str) -> str:
    block = document.get(section)
    value = block.get(key) if isinstance(block, Mapping) else None
    if not isinstance(value, str) or not value:
        raise UnregisteredArtifact(
            f"the accepted publication states no {section}.{key} for the control"
        )
    return value


def _contained_regular_file(locator: str) -> Path:
    root = resolve_model_root().resolve()
    candidate = Path(locator)
    resolved = candidate.resolve()
    if not resolved.is_relative_to(root):
        raise UnregisteredArtifact(
            f"{locator} resolves outside the registered model root {root}"
        )
    for component in (candidate, *candidate.parents):
        if component.is_symlink():
            raise UnregisteredArtifact(f"{locator} reaches its bytes through symlink {component}")
    if not resolved.is_file():
        raise UnregisteredArtifact(f"{locator} is not a regular file")
    return resolved


def _stat_tuple(path: Path) -> tuple[int, int, int, int]:
    status = os.stat(path)
    return (status.st_dev, status.st_ino, status.st_mtime_ns, status.st_size)


def _digest_of(path: Path) -> str:
    key = (str(path), _stat_tuple(path))
    cached = _digest_cache.get(key)
    if cached is not None:
        return cached
    digest = file_sha256(path)
    _remember(_digest_cache, key, digest)
    return digest


def _remember(cache: dict[Any, Any], key: Any, value: Any) -> None:
    if len(cache) >= _DIGEST_CACHE_LIMIT:
        cache.pop(next(iter(cache)))
    cache[key] = value


def _collect(pin: PinnedControl, frame: pl.LazyFrame) -> pl.DataFrame:
    """Read, then prove the bytes did not move underneath the read.

    `polars.scan_parquet` takes a path rather than a descriptor, so containment cannot be held
    open across the read; a swap that lands and is reverted inside one request stays invisible.
    """
    before = _stat_tuple(pin.artifact_path)
    collected = frame.collect()
    if _stat_tuple(pin.artifact_path) != before:
        raise UnregisteredArtifact(
            f"{pin.artifact_path} changed while it was being read for"
            f" publication {pin.publication_id}"
        )
    return collected


def reasons(value: str | None) -> tuple[str, ...]:
    """The pipe-joined reason set as served: sorted, deduplicated, never a bare string."""
    if not value:
        return ()
    return tuple(sorted({item for item in value.split("|") if item}))


def cache_state() -> tuple[int, int]:
    """Entry counts, for the tests that assert the digest cache invalidates rather than grows."""
    return (len(_digest_cache), len(_coverage_cache))


def clear_caches() -> None:
    _digest_cache.clear()
    _coverage_cache.clear()
