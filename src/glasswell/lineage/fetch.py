"""fetch_raw(): bytes into the raw zone, a manifest row, and the derivation that links them.

Layout is SB-07 §2.3 under SB-06's root (plan conflict C1). The raw zone is the truth and
Postgres is the index: `manifest.json` beside each payload is the byte-identical row.
"""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

import httpx
import psycopg
from psycopg.rows import dict_row

from glasswell.lineage.audit import emit
from glasswell.lineage.capture import current_session, derive
from glasswell.lineage.ftp import FTP, download_ftp, remote_path_from_url
from glasswell.lineage.manifests import register_manifest
from glasswell.lineage.models import AcquisitionMethod, ManifestRecord, OutputSpec
from glasswell.lineage.serialization import canonical_json, json_ready

RAW_ROOT_ENV = "GLASSWELL_RAW_ROOT"
# SB-01 §1.2: the EMNRD page publishes the address as an image, so the pin is a config line and
# a move is an audit event. Recorded on every ftp_anon manifest so the pin's provenance travels.
HOST_RESOLVED_FROM = "pinned_config"
DEFAULT_RAW_ROOT = Path("data/raw")
MANIFEST_FILENAME = "manifest.json"
SHA256_MANIFEST_FILENAME = "MANIFEST.sha256"
PAYLOAD_STEM = "payload"
FILE_MODE = 0o444
DIRECTORY_MODE = 0o555

_CHUNK_BYTES = 1 << 20
_SLUG_RE = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True, slots=True)
class FetchResult:
    manifest: ManifestRecord
    created: bool
    unchanged: bool
    payload_path: Path


@dataclass(frozen=True, slots=True)
class _Download:
    """What a transport hands the registrar: the bytes, and what the far end said about them."""

    path: Path
    sha256: str
    size_bytes: int
    acquisition_params: dict[str, Any]
    upstream_mtime: datetime | None = None
    upstream_etag: str | None = None
    media_type: str | None = None


def resolve_raw_root(explicit: Path | str | None = None) -> Path:
    """Explicit argument, then `GLASSWELL_RAW_ROOT`, then a repo-local default — never /srv."""
    if explicit is not None:
        return Path(explicit)
    return Path(os.environ.get(RAW_ROOT_ENV) or DEFAULT_RAW_ROOT)


def _slug(source_key: str) -> str:
    return _SLUG_RE.sub("-", source_key.lower()).strip("-") or "artifact"


def _extension(source_key: str) -> str:
    return Path(source_key).suffix or ".bin"


def _download_to(url: str, destination: Path, client: httpx.Client | None) -> _Download:
    session = client or httpx.Client(follow_redirects=True, timeout=60.0)
    digest = hashlib.sha256()
    size = 0
    try:
        with session.stream("GET", url) as response:
            response.raise_for_status()
            with destination.open("wb") as handle:
                for chunk in response.iter_bytes(_CHUNK_BYTES):
                    digest.update(chunk)
                    size += len(chunk)
                    handle.write(chunk)
            headers = dict(response.headers)
            return _Download(
                path=destination,
                sha256=digest.hexdigest(),
                size_bytes=size,
                acquisition_params={
                    "status": response.status_code,
                    "content_length": headers.get("content-length"),
                    "etag": headers.get("etag"),
                    "last_modified": headers.get("last-modified"),
                    "redirect_chain": [str(previous.url) for previous in response.history],
                },
                upstream_mtime=_upstream_mtime(headers),
                upstream_etag=headers.get("etag"),
                media_type=headers.get("content-type"),
            )
    finally:
        if client is None:
            session.close()


def _download_ftp_to(url: str, destination: Path, connection: FTP | None) -> _Download:
    """`ftp_anon` (SB-07 §2.4): the host is pinned by the caller and never re-resolved here."""
    host, remote_path = remote_path_from_url(url)
    download = download_ftp(host, remote_path, destination, connection=connection)
    return _Download(
        path=destination,
        sha256=download.sha256,
        size_bytes=download.size_bytes,
        acquisition_params={
            "host": download.host,
            "path": download.remote_path,
            "mdtm": download.mdtm,
            "size_reported": download.size_reported,
            "host_resolved_from": HOST_RESOLVED_FROM,
        },
        upstream_mtime=download.upstream_mtime,
    )


def _upstream_mtime(headers: Mapping[str, str]) -> datetime | None:
    raw = headers.get("last-modified")
    if not raw:
        return None
    try:
        return parsedate_to_datetime(raw)
    except (TypeError, ValueError):  # a malformed upstream date is not a fetch failure
        return None


def _artifact_directory(
    root: Path, source_id: str, source_key: str, vintage: date, fetched_at: datetime, sha256: str
) -> Path:
    stamp = f"{vintage.isoformat()}T{fetched_at.strftime('%H%M%S')}Z-{sha256[:12]}"
    return root / source_id / _slug(source_key) / stamp


def _existing_storage_uri(connection: psycopg.Connection, sha256: str) -> str | None:
    with connection.cursor() as cursor:
        cursor.execute("select storage_uri from lineage.manifests where sha256 = %s", (sha256,))
        row = cursor.fetchone()
    return row[0] if row else None


def _link_fetch_derivation(
    connection: psycopg.Connection, manifest_id: str, derivation_id: str
) -> ManifestRecord:
    """Set after the derive block: the FK needs the derivation row to exist first."""
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            "update lineage.manifests set fetch_derivation_id = %s"
            " where manifest_id = %s returning *",
            (derivation_id, manifest_id),
        )
        row = cursor.fetchone()
    if row is None:
        raise RuntimeError(f"manifest {manifest_id} vanished between insert and link")
    return ManifestRecord(**dict(row))


def _write_manifest_json(directory: Path, manifest: ManifestRecord) -> Path:
    path = directory / MANIFEST_FILENAME
    path.write_bytes(canonical_json(json_ready(manifest.model_dump())))
    return path


def _file_sha256(path: Path) -> str:
    """Chunked: NM's production artifact is 968 MB, and read_bytes() would hold all of it."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(_CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_sha256_manifest(directory: Path) -> Path:
    """SB-06 §3.3: a restored vintage verifies with `sha256sum -c` and no external state."""
    names = sorted(
        entry.name
        for entry in directory.iterdir()
        if entry.is_file() and entry.name != SHA256_MANIFEST_FILENAME
    )
    lines = [f"{_file_sha256(directory / name)}  {name}\n" for name in names]
    path = directory / SHA256_MANIFEST_FILENAME
    path.write_text("".join(lines), encoding="utf-8")
    return path


def _seal(directory: Path) -> None:
    for entry in directory.iterdir():
        entry.chmod(FILE_MODE)
    directory.chmod(DIRECTORY_MODE)


def fetch_raw(
    connection: psycopg.Connection,
    source_id: str,
    source_key: str,
    *,
    url: str,
    acquisition_method: AcquisitionMethod = "https_get",
    raw_root: Path | str | None = None,
    client: httpx.Client | None = None,
    ftp: FTP | None = None,
    rules: Sequence[str] = (),
    media_type: str | None = None,
    license_note: str | None = None,
    redistributable: bool = False,
    extra_acquisition_params: Mapping[str, Any] | None = None,
    decompressed_inventory: Callable[[Path], Sequence[Mapping[str, Any]]] | None = None,
) -> FetchResult:
    """Fetch an artifact idempotently by content hash; identical bytes re-register as a check."""
    root = resolve_raw_root(raw_root)
    staging = root / ".incoming"
    staging.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=staging, prefix="fetch-")
    os.close(handle)
    temporary_path = Path(temporary)

    params = {
        "url": url,
        "acquisition_method": acquisition_method,
        "source_id": source_id,
        "source_key": source_key,
        **dict(extra_acquisition_params or {}),
    }

    try:
        try:
            if acquisition_method == "ftp_anon":
                download = _download_ftp_to(url, temporary_path, ftp)
            else:
                download = _download_to(url, temporary_path, client)
        except (httpx.HTTPError, OSError) as error:
            emit(
                connection,
                "raw.fetch_failed",
                subject_type="manifest",
                subject_id=f"{source_id}/{source_key}",
                payload={
                    "url": url,
                    # A transport that names its own failure mode says so; everything else
                    # keeps the class name this ledger has recorded since P1.
                    "reason": getattr(error, "glasswell_reason", type(error).__name__),
                    "detail": str(error),
                },
            )
            raise
        # Self-stamped from the run's clock, never the wall. `fetched_at` is when the bytes
        # landed; the vintage is the run's, so a fetch that crosses midnight still stamps the
        # day its run opened — the vintage is part of the key a restatement lands on (DIR-9, B2).
        session = current_session()
        fetched_at = session.clock.now()
        vintage = session.vintage
        inventory = list(decompressed_inventory(download.path)) if decompressed_inventory else []

        # The bytes that arrived are part of this fetch's address; changed upstream bytes are
        # the common path (§2.1), and a spec blind to them would read as a determinism failure.
        output = OutputSpec(
            store="file",
            dataset=f"raw.{source_id}",
            partition={"source_key": source_key, "sha256": download.sha256[:12]},
        )
        with derive("raw.fetch", output=output, params=params, rules=rules) as context:
            context.set_output_hash(download.sha256)
            existing = _existing_storage_uri(connection, download.sha256)
            if existing is None:
                directory = _artifact_directory(
                    root, source_id, source_key, vintage, fetched_at, download.sha256
                )
                directory.mkdir(parents=True, exist_ok=True)
                payload_path = directory / f"{PAYLOAD_STEM}{_extension(source_key)}"
                os.replace(temporary_path, payload_path)
            else:
                payload_path = Path(existing)

            registration = register_manifest(
                connection,
                sha256=download.sha256,
                size_bytes=download.size_bytes,
                source_id=source_id,
                source_key=source_key,
                acquisition_url=url,
                acquisition_method=acquisition_method,
                acquisition_params={
                    **download.acquisition_params,
                    **dict(extra_acquisition_params or {}),
                },
                fetched_at=fetched_at,
                fetch_vintage=vintage,
                storage_uri=str(payload_path),
                media_type=media_type or download.media_type,
                upstream_mtime=download.upstream_mtime,
                upstream_etag=download.upstream_etag,
                decompressed_inventory=inventory,
                license_note=license_note,
                redistributable=redistributable,
            )
    finally:
        temporary_path.unlink(missing_ok=True)

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
