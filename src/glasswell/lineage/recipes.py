"""Recipes (SB-07 §4.1): the closure that regenerates an artifact, content-addressed.

`replay()` is deliberately absent — SB-07 §4.5 makes replay a CLI path, and the CLI is not
in this slice.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, get_args

import psycopg
from psycopg.types.json import Jsonb

from glasswell.lineage.models import DeterminismClass, InputRef, Operation
from glasswell.lineage.serialization import hash_payload, json_ready

RECIPE_PREFIX = "rcp_"


def build_recipe(
    connection: psycopg.Connection,
    operation: str,
    *,
    code_version: str,
    lockfile_sha256: str | None,
    entry_point: str,
    params: Mapping[str, Any],
    input_manifest_ids: Sequence[str] = (),
    input_refs: Sequence[InputRef | Mapping[str, Any]] = (),
    output: Mapping[str, Any] | None = None,
    seed: int | None = None,
    determinism_class: str = "D1",
) -> str:
    """Content-address a recipe document and store it; identical closures reuse one row."""
    if operation not in get_args(Operation):
        raise ValueError(f"{operation!r} is not a declared operation")
    if determinism_class not in get_args(DeterminismClass):
        raise ValueError(f"{determinism_class!r} is not a declared determinism class")

    document: dict[str, Any] = {
        "operation": operation,
        "entry_point": entry_point,
        "params": json_ready(dict(params)),
        "params_hash": hash_payload(params),
        "code_version": code_version,
        "environment": {"lockfile_sha256": lockfile_sha256},
        "inputs": [
            *({"kind": "manifest", "id": manifest} for manifest in input_manifest_ids),
            *(
                json_ready(ref.model_dump(mode="json") if isinstance(ref, InputRef) else dict(ref))
                for ref in input_refs
            ),
        ],
        "seeds": {} if seed is None else {"global": seed},
        "determinism_class": determinism_class,
    }
    if output is not None:
        document["output"] = json_ready(dict(output))
    recipe_id = RECIPE_PREFIX + hash_payload(document)[:32]
    document = {"recipe_id": recipe_id, **document, "replay": f"glasswell repro {recipe_id}"}

    with connection.cursor() as cursor:
        cursor.execute(
            "insert into lineage.recipes (recipe_id, operation, document)"
            " values (%s, %s, %s) on conflict (recipe_id) do nothing",
            (recipe_id, operation, Jsonb(document)),
        )
    return recipe_id
