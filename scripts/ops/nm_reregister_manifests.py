#!/usr/bin/env python3
"""Re-register a sealed raw-zone artifact into an index that does not carry it yet.

No socket is opened to the upstream: the sidecar beside the payload is byte-identical to the
row the fetch wrote (`lineage/fetch.py`), and `register_manifest` is idempotent on the sha256
within a slot, so running this against an index that already holds the artifact is a recorded
check rather than a second row.

Vendored from `/data/scratch/d1-p4/reregister.py` on VM 111; the divergences from that
original are enumerated in `work-output/t3-p1-status.md`, which carries it verbatim.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

import psycopg
from psycopg.conninfo import conninfo_to_dict

from glasswell.lineage.errors import ManifestConflict
from glasswell.lineage.ids import manifest_id
from glasswell.lineage.manifests import owning_slot, register_manifest

REQUIRED_KEYS = (
    "sha256",
    "bytes",
    "source_id",
    "source_key",
    "acquisition_url",
    "acquisition_method",
    "acquisition_params",
    "fetched_at",
    "fetch_vintage",
    "storage_uri",
    "media_type",
    "upstream_mtime",
    "upstream_etag",
    "decompressed_inventory",
    "license_note",
    "redistributable",
)


class SidecarError(Exception):
    """A sidecar this tool cannot read. Named by path so nine files stay distinguishable."""


def read_sidecar(path: Path) -> dict[str, Any]:
    """The sidecar's own schema, validated before anything opens a transaction."""
    try:
        row = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise SidecarError(f"{path}: cannot be read: {error}") from error
    except json.JSONDecodeError as error:
        raise SidecarError(f"{path}: is not JSON: {error}") from error
    if not isinstance(row, dict):
        raise SidecarError(f"{path}: is not a JSON object")
    missing = [key for key in REQUIRED_KEYS if key not in row]
    if missing:
        raise SidecarError(f"{path}: missing required key(s): {', '.join(missing)}")
    try:
        manifest_id(row["sha256"])
    except ValueError as error:
        raise SidecarError(f"{path}: {error}") from error
    try:
        datetime.fromisoformat(row["fetched_at"])
        date.fromisoformat(row["fetch_vintage"])
        if row["upstream_mtime"]:
            datetime.fromisoformat(row["upstream_mtime"])
    except (TypeError, ValueError) as error:
        raise SidecarError(f"{path}: unparseable timestamp: {error}") from error
    return row


def register(connection: psycopg.Connection, path: Path, row: dict[str, Any]) -> str:
    # register_manifest carries no fetch_derivation_id here: the NM raw.fetch derivations live
    # in glasswell_d1, so a re-registered manifest resolves to its bytes and acquisition_params
    # but not to the fetch that produced them. See docs/runbook-nm-promotion.md; do not re-fetch.
    registration = register_manifest(
        connection,
        sha256=row["sha256"],
        size_bytes=row["bytes"],
        source_id=row["source_id"],
        source_key=row["source_key"],
        acquisition_url=row["acquisition_url"],
        acquisition_method=row["acquisition_method"],
        acquisition_params=row["acquisition_params"],
        fetched_at=datetime.fromisoformat(row["fetched_at"]),
        fetch_vintage=date.fromisoformat(row["fetch_vintage"]),
        storage_uri=row["storage_uri"],
        media_type=row["media_type"],
        upstream_mtime=(
            datetime.fromisoformat(row["upstream_mtime"]) if row["upstream_mtime"] else None
        ),
        upstream_etag=row["upstream_etag"],
        decompressed_inventory=row["decompressed_inventory"],
        license_note=row["license_note"],
        redistributable=row["redistributable"],
    )
    identifier = registration.manifest.manifest_id
    if registration.created:
        superseded = registration.superseded_manifest_id or "nothing"
        print(f"{identifier} registered {path} supersedes={superseded}")
    else:
        print(f"{identifier} already present {path}")
    return identifier


def inspect(connection: psycopg.Connection, path: Path, row: dict[str, Any]) -> str:
    """The dry-run report: what a real run would do, resolved against the live index."""
    identifier = manifest_id(row["sha256"])
    owner = owning_slot(connection, row["sha256"])
    if owner is None:
        print(f"{identifier} would register {path}")
    elif (owner["source_id"], owner["source_key"]) != (row["source_id"], row["source_key"]):
        raise ManifestConflict(
            row["sha256"],
            (owner["source_id"], owner["source_key"]),
            (row["source_id"], row["source_key"]),
            owner["bytes"],
        )
    else:
        print(f"{identifier} already present {path}")
    return identifier


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Re-register sealed raw-zone artifacts from their sidecars."
    )
    parser.add_argument("--dsn", required=True, help="target database; name it, never default it")
    parser.add_argument(
        "--sidecar",
        required=True,
        action="append",
        metavar="PATH",
        help="a manifest.json beside a sealed payload; repeatable",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="validate every sidecar and report the manifest ids, committing nothing",
    )
    args = parser.parse_args(argv)

    paths = [Path(sidecar) for sidecar in args.sidecar]
    try:
        rows = [(path, read_sidecar(path)) for path in paths]
    except SidecarError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    try:
        target = conninfo_to_dict(args.dsn)
    except psycopg.ProgrammingError as error:
        print(f"error: --dsn is unparseable: {error}", file=sys.stderr)
        return 1
    # glasswell and glasswell_d1 are one letter apart and only one of them is production.
    print(
        f"target database={target.get('dbname', '(unnamed)')}"
        f" host={target.get('host', '(default)')}"
        f" mode={'dry-run' if args.dry_run else 'register'}"
    )

    with psycopg.connect(args.dsn) as connection:
        # A dry run that cannot write is a stronger promise than one that chooses not to.
        connection.read_only = args.dry_run
        for path, row in rows:
            try:
                if args.dry_run:
                    inspect(connection, path, row)
                else:
                    register(connection, path, row)
            except ManifestConflict as error:
                connection.rollback()
                print(f"error: {path}: {error}", file=sys.stderr)
                return 1
        if args.dry_run:
            connection.rollback()
        else:
            connection.commit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
