"""Raw-zone manifest registration (SB-07 §2.1). Identity is the content hash."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from glasswell.lineage.audit import emit
from glasswell.lineage.errors import ManifestConflict
from glasswell.lineage.ids import manifest_id
from glasswell.lineage.models import AcquisitionMethod, ManifestRecord
from glasswell.lineage.serialization import json_ready


@dataclass(frozen=True, slots=True)
class ManifestRegistration:
    manifest: ManifestRecord
    created: bool
    superseded_manifest_id: str | None


_INSERT = """
insert into lineage.manifests (
    manifest_id, sha256, bytes, source_id, source_key, acquisition_url, acquisition_method,
    acquisition_params, fetched_at, fetch_vintage, upstream_mtime, upstream_etag, media_type,
    decompressed_inventory, supersedes_manifest_id, storage_uri, license_note, redistributable,
    fetch_derivation_id)
values (%(manifest_id)s, %(sha256)s, %(bytes)s, %(source_id)s, %(source_key)s,
        %(acquisition_url)s, %(acquisition_method)s, %(acquisition_params)s, %(fetched_at)s,
        %(fetch_vintage)s, %(upstream_mtime)s, %(upstream_etag)s, %(media_type)s,
        %(decompressed_inventory)s, %(supersedes_manifest_id)s, %(storage_uri)s,
        %(license_note)s, %(redistributable)s, %(fetch_derivation_id)s)
returning *
"""


def owning_slot(connection: psycopg.Connection, sha256: str) -> dict[str, Any] | None:
    """The slot already holding these bytes, if any. `sha256` is unique, so there is at most
    one, and a second claimant is a conflict rather than a duplicate (F8)."""
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            "select source_id, source_key, storage_uri, bytes from lineage.manifests"
            " where sha256 = %s",
            (sha256,),
        )
        return cursor.fetchone()


def register_manifest(
    connection: psycopg.Connection,
    *,
    sha256: str,
    size_bytes: int,
    source_id: str,
    source_key: str,
    acquisition_url: str,
    acquisition_method: AcquisitionMethod,
    fetched_at: datetime,
    fetch_vintage: date | None = None,
    acquisition_params: Mapping[str, Any] | None = None,
    storage_uri: str = "",
    media_type: str | None = None,
    upstream_mtime: datetime | None = None,
    upstream_etag: str | None = None,
    decompressed_inventory: Sequence[Mapping[str, Any]] = (),
    license_note: str | None = None,
    redistributable: bool = False,
    fetch_derivation_id: str | None = None,
    correlation_id: str | None = None,
) -> ManifestRegistration:
    """Idempotent by sha256 *within a slot*: identical bytes re-register as a recorded check,
    not a new row. Identical bytes from another slot raise `ManifestConflict` (F8).

    Changed bytes under the same (source_id, source_key) create a new manifest that supersedes
    the current head — the common path, not an exception branch (§2.1).
    """
    identifier = manifest_id(sha256)
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            "select * from lineage.manifests where sha256 = %s for update", (sha256,)
        )
        existing = cursor.fetchone()
        if existing is not None:
            if (existing["source_id"], existing["source_key"]) != (source_id, source_key):
                raise ManifestConflict(
                    sha256,
                    (existing["source_id"], existing["source_key"]),
                    (source_id, source_key),
                    existing["bytes"],
                )
            emit(
                connection,
                "raw.fetch_verified_unchanged",
                subject_type="manifest",
                subject_id=identifier,
                payload={"source_id": source_id, "source_key": source_key},
                correlation_id=correlation_id,
                occurred_at=fetched_at,
            )
            return ManifestRegistration(
                manifest=_to_record(existing), created=False, superseded_manifest_id=None
            )

        cursor.execute(
            "select manifest_id from lineage.manifest_head"
            " where source_id = %s and source_key = %s",
            (source_id, source_key),
        )
        head = cursor.fetchone()
        superseded = head["manifest_id"] if head else None

        cursor.execute(
            _INSERT,
            {
                "manifest_id": identifier,
                "sha256": sha256,
                "bytes": size_bytes,
                "source_id": source_id,
                "source_key": source_key,
                "acquisition_url": acquisition_url,
                "acquisition_method": acquisition_method,
                "acquisition_params": Jsonb(json_ready(dict(acquisition_params or {}))),
                "fetched_at": fetched_at,
                "fetch_vintage": fetch_vintage or fetched_at.date(),
                "upstream_mtime": upstream_mtime,
                "upstream_etag": upstream_etag,
                "media_type": media_type,
                "decompressed_inventory": Jsonb(json_ready(list(decompressed_inventory))),
                "supersedes_manifest_id": superseded,
                "storage_uri": storage_uri,
                "license_note": license_note,
                "redistributable": redistributable,
                "fetch_derivation_id": fetch_derivation_id,
            },
        )
        inserted = cursor.fetchone()

    if inserted is None:
        raise RuntimeError(f"manifest insert for {identifier} returned no row")
    emit(
        connection,
        "raw.manifest_created",
        subject_type="manifest",
        subject_id=identifier,
        payload={"source_id": source_id, "source_key": source_key, "bytes": size_bytes},
        correlation_id=correlation_id,
        occurred_at=fetched_at,
    )
    if superseded is not None:
        emit(
            connection,
            "raw.manifest_superseded",
            subject_type="manifest",
            subject_id=superseded,
            payload={"superseded_by": identifier},
            correlation_id=correlation_id,
            occurred_at=fetched_at,
        )
    return ManifestRegistration(
        manifest=_to_record(inserted), created=True, superseded_manifest_id=superseded
    )


def manifest_chain(connection: psycopg.Connection, manifest: str) -> list[str]:
    """Supersession chain, newest first. Chains are never broken or rewritten (§2.5)."""
    with connection.cursor() as cursor:
        cursor.execute(
            "with recursive chain as ("
            "  select manifest_id, supersedes_manifest_id from lineage.manifests"
            "   where manifest_id = %s"
            "  union all"
            "  select m.manifest_id, m.supersedes_manifest_id from lineage.manifests m"
            "    join chain c on m.manifest_id = c.supersedes_manifest_id)"
            " select manifest_id from chain",
            (manifest,),
        )
        return [row[0] for row in cursor.fetchall()]


def _to_record(row: Mapping[str, Any]) -> ManifestRecord:
    return ManifestRecord(**dict(row))
