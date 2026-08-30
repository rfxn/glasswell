"""Lineage records for figures computed by an API request rather than read from one row."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from glasswell.ingest.base import resolve_environment
from glasswell.lineage.capture import derive, lineage_session
from glasswell.lineage.envelope import Figure, Series
from glasswell.lineage.ids import format_selector, parse_selector
from glasswell.lineage.models import InputRef, OutputSpec
from glasswell.lineage.serialization import hash_payload, json_ready
from glasswell.lineage.store import PostgresRecorder


def register_response_figures(
    connection: psycopg.Connection,
    data: Any,
    *,
    dataset: str,
    operation_id: str,
    locator: str,
    partition: Mapping[str, str],
    input_derivations: Sequence[str],
    correlation_id: str,
    rule_ids: Sequence[str] = (),
) -> Any:
    """Persist exact selector/value evidence, then bind every response figure to it."""
    outputs = _selector_outputs(data)
    if not outputs:
        return data
    output_partition = (
        {"request_selector": _normal_selector(format_selector(sorted(partition.items())))}
        if partition
        else {}
    )
    inputs = _input_refs(connection, input_derivations)
    rules = sorted(set(rule_ids))
    params = {"operation_id": operation_id}
    try:
        environment = resolve_environment(connection)
        lock_identity = hash_payload(
            {
                "dataset": dataset,
                "partition": output_partition,
                "params": params,
                "inputs": [item.model_dump(mode="json") for item in inputs],
                "rules": rules,
                "code_version": environment.code_version,
                "env_id": environment.env_id,
            }
        )
        with connection.cursor() as cursor:
            cursor.execute(
                "select pg_advisory_xact_lock(hashtextextended(%s, 0))", (lock_identity,)
            )
        with (
            lineage_session(
                recorder=PostgresRecorder(connection, lock_existing=False),
                environment=environment,
                correlation_id=correlation_id,
            ),
            derive(
                "api.respond",
                output=OutputSpec(
                    store="response",
                    dataset=dataset,
                    partition=output_partition,
                    locator=locator,
                    schema_version="1",
                ),
                params=params,
                inputs=inputs,
                rules=rules,
                ttl_class="ephemeral",
                determinism_class="D3",
            ) as context,
        ):
            context.set_output_hash(hash_payload(outputs))
            context.set_rows(len(outputs))
        _record_response_outputs(connection, context.derivation_id, outputs)
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    return _bind_derivation(data, context.derivation_id)


def _record_response_outputs(
    connection: psycopg.Connection,
    derivation_id: str,
    outputs: Mapping[str, Mapping[str, Any]],
) -> None:
    with connection.cursor() as cursor:
        cursor.executemany(
            "insert into lineage.response_selector_outputs"
            " (derivation_id, selector, evidence) values (%s, %s, %s)"
            " on conflict (derivation_id, selector) do nothing",
            [
                (derivation_id, selector, Jsonb(evidence))
                for selector, evidence in outputs.items()
            ],
        )
        cursor.execute(
            "select selector, evidence from lineage.response_selector_outputs"
            " where derivation_id = %s order by selector",
            (derivation_id,),
        )
        recorded = {row[0]: row[1] for row in cursor.fetchall()}
    if recorded != dict(outputs):
        raise ValueError("recorded API-response selector evidence does not match the output")


def _input_refs(connection: psycopg.Connection, derivation_ids: Sequence[str]) -> list[InputRef]:
    identifiers = sorted(set(derivation_ids))
    if not identifiers:
        return []
    with connection.cursor() as cursor:
        cursor.execute(
            "select derivation_id, created_vintage from lineage.derivations"
            " where derivation_id = any(%s) order by derivation_id",
            (identifiers,),
        )
        found = cursor.fetchall()
    if len(found) != len(identifiers):
        resolved = {row[0] for row in found}
        missing = sorted(set(identifiers) - resolved)
        raise ValueError(f"response input derivations are not registered: {missing}")
    return [InputRef(kind="derivation", ref_id=row[0], as_of_vintage=row[1]) for row in found]


def _selector_outputs(node: Any) -> dict[str, dict[str, Any]]:
    outputs: dict[str, dict[str, Any]] = {}

    def visit(value: Any) -> None:
        if isinstance(value, Figure):
            if value.selector is None:
                raise ValueError("an API-response figure must carry a selector")
            selector = _normal_selector(value.selector)
            evidence = json_ready({"value": value.value, "unit": value.unit})
            prior = outputs.setdefault(selector, evidence)
            if prior != evidence:
                raise ValueError(f"selector {selector!r} names conflicting response figures")
        # Before the Sequence branch, not after: Series.values is a Sequence, so a Series
        # reached as a list would be walked element-wise and its evidence never recorded.
        elif isinstance(value, Series):
            if value.selector is None:
                raise ValueError("an API-response series must carry a selector")
            if value.point_handles is not None:
                raise ValueError("an API-response series may not carry point handles")
            selector = _normal_selector(value.selector)
            evidence = json_ready({"values": list(value.values), "unit": value.unit})
            prior = outputs.setdefault(selector, evidence)
            if prior != evidence:
                raise ValueError(f"selector {selector!r} names conflicting response figures")
        elif isinstance(value, Mapping):
            for child in value.values():
                visit(child)
        elif isinstance(value, (list, tuple)):
            for child in value:
                visit(child)

    visit(node)
    return dict(sorted(outputs.items()))


def _bind_derivation(node: Any, derivation_id: str) -> Any:
    if isinstance(node, (Figure, Series)):
        return node.model_copy(update={"derivation": derivation_id})
    if isinstance(node, Mapping):
        return {key: _bind_derivation(value, derivation_id) for key, value in node.items()}
    if isinstance(node, list):
        return [_bind_derivation(value, derivation_id) for value in node]
    if isinstance(node, tuple):
        return tuple(_bind_derivation(value, derivation_id) for value in node)
    return node


def _normal_selector(selector: str) -> str:
    return format_selector(sorted(parse_selector(selector)))
