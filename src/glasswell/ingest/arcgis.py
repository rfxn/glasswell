"""arcgis_rest_paginate: the sanctioned REST harvest (SB-01 §1.2.1, blueprint v0.6 §4E.7).

A payload assembled from a paginated service is a raw artifact like any other: one declared
total order, one SHA-256, one manifest, a self-stamped vintage. The walk asserts the service's
own record count before and after, and a disagreement fails the fetch with no manifest written.
Registers through the same registrar path as fetch_raw so the artifact layout, sealing and
derivation shape stay single-sourced; the fetch machinery itself is untouched (SB-07 H11 owns
the enum value this method records).
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx
import psycopg

from glasswell.lineage.audit import emit
from glasswell.lineage.capture import current_session, derive
from glasswell.lineage.fetch import (
    FetchResult,
    _link_fetch_derivation,
    _seal,
    _write_manifest_json,
    _write_sha256_manifest,
    resolve_raw_root,
    stage_payload,
)
from glasswell.lineage.fetch_attempts import sanitized_failure_detail, source_poll
from glasswell.lineage.manifests import register_manifest
from glasswell.lineage.models import OutputSpec

# SB-01 §1.2.1: hosts are allowlisted by amendment with their verification evidence, never by
# a code change. This tuple mirrors the blueprint table; editing it without the amendment is
# the reviewability failure §4E.7 names.
ALLOWED_HOSTS: tuple[str, ...] = (
    "gis.blm.gov",
    "ndgishub.nd.gov",
    "gis.emnrd.nm.gov",
    "mapservice.nmstatelands.org",
    "services1.arcgis.com",
)

ARTIFACT_MEDIA_TYPE = "application/x-ndjson"
PAGE_FORMAT = "geojson"
# One connection per host, pages issued serially, a minimum inter-request delay, and the
# project User-Agent (§1.3, v0.6 §4E.6).
PAGE_DELAY_SECONDS = 0.25
USER_AGENT = "glasswell (data platform; ryan@rfxn.com)"
_TOKEN_GATED_CODES = frozenset({403, 429, 499})
_OID_FIELD_TYPE = "esriFieldTypeOID"


class ArcGisFetchError(RuntimeError):
    """Base for §1.2.1 failures; glasswell_reason is what raw.fetch_failed records."""

    glasswell_reason = "arcgis_fetch_failed"


class HostNotAllowlisted(ArcGisFetchError):
    glasswell_reason = "host_not_allowlisted"


class HostTokenGated(ArcGisFetchError):
    """A 499/403/429 halts the service path: no sibling retry, no fallback mirror."""

    glasswell_reason = "host_token_gated"


class PageWalkIncomplete(ArcGisFetchError):
    """The walk and the service's own count disagree; a partial harvest must fail loudly."""

    glasswell_reason = "page_walk_incomplete"


class LayerNotPaginable(ArcGisFetchError):
    """A layer that does not advertise supportsPagination is not an ingest path."""

    glasswell_reason = "layer_not_paginable"


class EmptyWalk(ArcGisFetchError):
    """A layer matching no features seals zero bytes, whose hash every empty harvest shares."""

    glasswell_reason = "empty_walk"


@dataclass(frozen=True, slots=True)
class LayerInfo:
    name: str
    object_id_field: str
    max_record_count: int
    supports_pagination: bool
    spatial_reference_wkid: int | None
    service_version: str
    layer_json_sha256: str


def _require_allowlisted(service_url: str) -> None:
    parts = urlsplit(service_url)
    if parts.scheme != "https":
        raise HostNotAllowlisted(
            f"{service_url} is not https; the allowlist authorises the TLS endpoint,"
            " not the host name"
        )
    host = parts.hostname or ""
    if host not in ALLOWED_HOSTS:
        raise HostNotAllowlisted(
            f"{host} is not on the SB-01 §1.2.1 allowlist; hosts move by amendment, not code"
        )


def _payload_json(response: httpx.Response) -> dict[str, Any]:
    """ArcGIS reports failure inside an HTTP 200, so the body is checked, not just the status."""
    if response.status_code in _TOKEN_GATED_CODES:
        raise HostTokenGated(f"{response.request.url} returned HTTP {response.status_code}")
    response.raise_for_status()
    payload = response.json()
    error = payload.get("error") if isinstance(payload, dict) else None
    if error:
        code = int(error.get("code", 0))
        message = f"{response.request.url} returned ArcGIS error {code}: {error.get('message')}"
        if code in _TOKEN_GATED_CODES:
            raise HostTokenGated(message)
        raise ArcGisFetchError(message)
    return payload


def _layer_info(client: httpx.Client, service_url: str, layer_id: int) -> LayerInfo:
    response = client.get(f"{service_url}/{layer_id}", params={"f": "json"})
    payload = _payload_json(response)
    advanced = payload.get("advancedQueryCapabilities") or {}
    object_id_field = payload.get("objectIdField") or next(
        (
            field["name"]
            for field in payload.get("fields", ())
            if field.get("type") == _OID_FIELD_TYPE
        ),
        "",
    )
    extent = payload.get("extent") or {}
    wkid = (extent.get("spatialReference") or {}).get("wkid")
    return LayerInfo(
        name=str(payload.get("name", "")),
        object_id_field=object_id_field,
        max_record_count=int(payload.get("maxRecordCount", 0)),
        supports_pagination=bool(
            payload.get("supportsPagination") or advanced.get("supportsPagination")
        ),
        spatial_reference_wkid=int(wkid) if wkid is not None else None,
        service_version=str(payload.get("currentVersion", "")),
        layer_json_sha256=hashlib.sha256(response.content).hexdigest(),
    )


def _count(client: httpx.Client, service_url: str, layer_id: int, where: str) -> int:
    response = client.get(
        f"{service_url}/{layer_id}/query",
        params={"where": where, "returnCountOnly": "true", "f": "json"},
    )
    return int(_payload_json(response)["count"])


def _page(
    client: httpx.Client,
    service_url: str,
    layer_id: int,
    *,
    where: str,
    order_by: str,
    offset: int,
    page_size: int,
    out_sr: int | None,
) -> list[dict[str, Any]]:
    params = {
        "where": where,
        "outFields": "*",
        "orderByFields": order_by,
        "resultOffset": str(offset),
        "resultRecordCount": str(page_size),
        "f": PAGE_FORMAT,
    }
    # Sent, not merely recorded: without outSR the BLM service returns WGS84-shifted geojson
    # (~1 m datum shift), and the manifest's out_sr claim would be false (gate-m14 C1).
    if out_sr is not None:
        params["outSR"] = str(out_sr)
    response = client.get(f"{service_url}/{layer_id}/query", params=params)
    payload = _payload_json(response)
    features = payload.get("features")
    if not isinstance(features, list):
        raise ArcGisFetchError(f"page at offset {offset} carries no feature list")
    return features


def arcgis_rest_paginate(
    connection: psycopg.Connection,
    source_id: str,
    source_key: str,
    *,
    service_url: str,
    layer_id: int,
    where: str,
    raw_root: Path | str | None = None,
    client: httpx.Client | None = None,
    page_size: int | None = None,
    page_delay_seconds: float = PAGE_DELAY_SECONDS,
    order_by: str | None = None,
    rules: tuple[str, ...] = (),
    license_note: str | None = None,
    redistributable: bool = False,
) -> FetchResult:
    """Walk one layer in total order and register the assembly as one raw artifact."""
    _require_allowlisted(service_url)
    correlation_id = current_session().correlation_id
    with source_poll(source_id, source_key, correlation_id=correlation_id) as attempt:
        result = _arcgis_rest_paginate(
            connection,
            source_id,
            source_key,
            service_url=service_url,
            layer_id=layer_id,
            where=where,
            raw_root=raw_root,
            client=client,
            page_size=page_size,
            page_delay_seconds=page_delay_seconds,
            order_by=order_by,
            rules=rules,
            license_note=license_note,
            redistributable=redistributable,
        )
        attempt.succeeded(
            created=result.created,
            manifest_id=result.manifest.manifest_id,
        )
        return result


def _arcgis_rest_paginate(
    connection: psycopg.Connection,
    source_id: str,
    source_key: str,
    *,
    service_url: str,
    layer_id: int,
    where: str,
    raw_root: Path | str | None = None,
    client: httpx.Client | None = None,
    page_size: int | None = None,
    page_delay_seconds: float = PAGE_DELAY_SECONDS,
    order_by: str | None = None,
    rules: tuple[str, ...] = (),
    license_note: str | None = None,
    redistributable: bool = False,
) -> FetchResult:
    root = resolve_raw_root(raw_root)
    staging = root / ".incoming"
    staging.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=staging, prefix="arcgis-")
    os.close(handle)
    temporary_path = Path(temporary)
    session = client or httpx.Client(
        follow_redirects=True, timeout=120.0, headers={"User-Agent": USER_AGENT}
    )
    params: dict[str, Any] = {
        "url": f"{service_url}/{layer_id}",
        "acquisition_method": "arcgis_rest_paginate",
        "source_id": source_id,
        "source_key": source_key,
    }

    try:
        try:
            result = _walk(
                session,
                temporary_path,
                service_url=service_url,
                layer_id=layer_id,
                where=where,
                page_size=page_size,
                page_delay_seconds=page_delay_seconds,
                order_by=order_by,
            )
        except (ArcGisFetchError, httpx.HTTPError, OSError, ValueError, KeyError) as error:
            emit(
                connection,
                "raw.fetch_failed",
                subject_type="manifest",
                subject_id=f"{source_id}/{source_key}",
                payload={
                    "url": params["url"],
                    "acquisition_method": "arcgis_rest_paginate",
                    "reason": getattr(error, "glasswell_reason", type(error).__name__),
                    "detail": sanitized_failure_detail(error),
                },
            )
            raise
        return _register(
            connection,
            source_id,
            source_key,
            root=root,
            temporary_path=temporary_path,
            walk=result,
            params=params,
            rules=rules,
            license_note=license_note,
            redistributable=redistributable,
        )
    finally:
        temporary_path.unlink(missing_ok=True)
        if client is None:
            session.close()


@dataclass(frozen=True, slots=True)
class _Walk:
    sha256: str
    size_bytes: int
    acquisition_params: dict[str, Any]


def _walk(
    client: httpx.Client,
    destination: Path,
    *,
    service_url: str,
    layer_id: int,
    where: str,
    page_size: int | None,
    page_delay_seconds: float,
    order_by: str | None = None,
) -> _Walk:
    layer = _layer_info(client, service_url, layer_id)
    if not layer.supports_pagination:
        raise LayerNotPaginable(f"{service_url}/{layer_id} does not advertise supportsPagination")
    if not (order_by or layer.object_id_field):
        raise ArcGisFetchError(f"{service_url}/{layer_id} names no object-id field to order by")
    if layer.max_record_count < 1:
        raise ArcGisFetchError(f"{service_url}/{layer_id} advertises maxRecordCount < 1")
    # Read from the layer JSON, never guessed and never exceeded (§1.2.1).
    size = layer.max_record_count if page_size is None else min(page_size, layer.max_record_count)
    # `resultOffset` re-runs the query per page, so the order must be a stable total order over
    # the source rows. A view-backed layer assigns OBJECTID per query and is not one (M1-9).
    order_by = order_by or f"{layer.object_id_field} ASC"

    count_before = _count(client, service_url, layer_id, where)
    if count_before == 0:
        raise EmptyWalk(f"{service_url}/{layer_id} matches no features for where={where!r}")
    expected_pages = math.ceil(count_before / size)
    digest = hashlib.sha256()
    written_bytes = 0
    features_written = 0
    pages = 0
    with destination.open("wb") as sink:
        for page_index in range(expected_pages):
            if page_index:
                time.sleep(page_delay_seconds)
            features = _page(
                client,
                service_url,
                layer_id,
                where=where,
                order_by=order_by,
                offset=page_index * size,
                page_size=size,
                out_sr=layer.spatial_reference_wkid,
            )
            if not features:
                break
            # One page, one line: re-serialised compact so the artifact is newline-delimited
            # by construction and byte-stable for identical upstream state (4E.7).
            line = (
                json.dumps(
                    {"type": "FeatureCollection", "features": features},
                    separators=(",", ":"),
                    ensure_ascii=False,
                ).encode("utf-8")
                + b"\n"
            )
            digest.update(line)
            written_bytes += len(line)
            sink.write(line)
            features_written += len(features)
            pages += 1
    count_after = _count(client, service_url, layer_id, where)

    if not (count_before == count_after == features_written and pages == expected_pages):
        raise PageWalkIncomplete(
            f"{service_url}/{layer_id}: count_before={count_before} count_after={count_after}"
            f" features_written={features_written} pages={pages} expected_pages={expected_pages}"
        )

    return _Walk(
        sha256=digest.hexdigest(),
        size_bytes=written_bytes,
        # The H11 acquisition_params shape, verbatim.
        acquisition_params={
            "service_url": service_url,
            "layer_id": layer_id,
            "layer_json_sha256": layer.layer_json_sha256,
            "service_version": layer.service_version,
            "where": where,
            "out_sr": layer.spatial_reference_wkid,
            "format": PAGE_FORMAT,
            "result_record_count": size,
            "order_by": order_by,
            "pages": pages,
            "count_before": count_before,
            "count_after": count_after,
            "features_written": features_written,
        },
    )


def _register(
    connection: psycopg.Connection,
    source_id: str,
    source_key: str,
    *,
    root: Path,
    temporary_path: Path,
    walk: _Walk,
    params: dict[str, Any],
    rules: tuple[str, ...],
    license_note: str | None,
    redistributable: bool,
) -> FetchResult:
    """The fetch_raw registrar sequence: derive, place, manifest, seal — one artifact."""
    session = current_session()
    fetched_at = session.clock.now()
    vintage = session.vintage
    output = OutputSpec(
        store="file",
        dataset=f"raw.{source_id}",
        partition={"source_key": source_key, "sha256": walk.sha256[:12]},
    )
    with derive("raw.fetch", output=output, params=params, rules=list(rules)) as context:
        context.set_output_hash(walk.sha256)
        payload_path = stage_payload(
            connection,
            sha256=walk.sha256,
            source_id=source_id,
            source_key=source_key,
            vintage=vintage,
            fetched_at=fetched_at,
            root=root,
            temporary_path=temporary_path,
            suffix=Path(source_key).suffix or ".bin",
        )

        registration = register_manifest(
            connection,
            sha256=walk.sha256,
            size_bytes=walk.size_bytes,
            source_id=source_id,
            source_key=source_key,
            acquisition_url=str(params["url"]),
            acquisition_method="arcgis_rest_paginate",
            acquisition_params=walk.acquisition_params,
            fetched_at=fetched_at,
            fetch_vintage=vintage,
            storage_uri=str(payload_path),
            media_type=ARTIFACT_MEDIA_TYPE,
            # A service publishes no vintage: self-stamped under v0.6 §4E.2, upstream_mtime
            # stays null and the register says so.
            upstream_mtime=None,
            license_note=license_note,
            redistributable=redistributable,
        )

    manifest = registration.manifest
    if registration.created:
        manifest = _link_fetch_derivation(connection, manifest.manifest_id, context.derivation_id)
        _write_manifest_json(payload_path.parent, manifest)
        _write_sha256_manifest(payload_path.parent)
        _seal(payload_path.parent)
    return FetchResult(
        manifest=manifest,
        created=registration.created,
        unchanged=not registration.created,
        payload_path=payload_path,
    )
