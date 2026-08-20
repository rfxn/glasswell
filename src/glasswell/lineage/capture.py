"""derive(): the single capture site for every artifact-producing transform (SB-07 §1.1)."""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from glasswell.lineage.clock import Clock, SystemClock
from glasswell.lineage.errors import LineageNotConfigured
from glasswell.lineage.ids import derivation_id, new_ulid
from glasswell.lineage.models import (
    DerivationRecord,
    DerivationStatus,
    DeriveEnvironment,
    DeterminismClass,
    InputRef,
    Operation,
    OutputSpec,
    RuleRef,
    TtlClass,
)
from glasswell.lineage.serialization import hash_payload
from glasswell.lineage.store import DerivationRecorder


@dataclass(frozen=True, slots=True)
class LineageSession:
    recorder: DerivationRecorder
    environment: DeriveEnvironment
    clock: Clock
    correlation_id: str


_SESSION: ContextVar[LineageSession | None] = ContextVar("glasswell_lineage_session", default=None)
_PARENT: ContextVar[DerivationContext | None] = ContextVar("glasswell_lineage_parent", default=None)


@dataclass(slots=True)
class DerivationContext:
    """Mutable handle a transform uses to declare what it read and what it produced."""

    operation: Operation
    output: OutputSpec
    params: Mapping[str, Any]
    model_id: str | None
    ttl_class: TtlClass
    determinism_class: DeterminismClass
    derivation_id: str = ""
    output_sha256: str | None = None
    output_rows: int | None = None
    _inputs: list[InputRef] = field(default_factory=list)
    _rules: list[RuleRef] = field(default_factory=list)

    def add_input(self, ref: InputRef) -> None:
        key = (ref.kind, ref.ref_id, ref.selector)
        if any((i.kind, i.ref_id, i.selector) == key for i in self._inputs):
            return
        self._inputs.append(ref.model_copy(update={"ord": len(self._inputs)}))

    def add_rule(self, rule_id: str, *, applied_rows: int | None = None) -> None:
        if any(r.rule_id == rule_id for r in self._rules):
            return
        self._rules.append(RuleRef(rule_id=rule_id, applied_rows=applied_rows))

    def set_output_hash(self, sha256_hex_digest: str) -> None:
        self.output_sha256 = sha256_hex_digest

    def set_rows(self, rows: int) -> None:
        self.output_rows = rows

    @property
    def inputs(self) -> tuple[InputRef, ...]:
        return tuple(self._inputs)

    @property
    def rules(self) -> tuple[RuleRef, ...]:
        return tuple(self._rules)

    def _knowledge_vintage(self) -> date | None:
        vintages = [i.as_of_vintage for i in self._inputs if i.as_of_vintage is not None]
        return max(vintages) if vintages else None


@contextmanager
def lineage_session(
    *,
    recorder: DerivationRecorder,
    environment: DeriveEnvironment,
    clock: Clock | None = None,
    correlation_id: str | None = None,
) -> Iterator[LineageSession]:
    """Bind the recorder, the pinned environment and the run's correlation id for this task."""
    resolved_clock = clock or SystemClock()
    session = LineageSession(
        recorder=recorder,
        environment=environment,
        clock=resolved_clock,
        correlation_id=correlation_id or new_ulid(resolved_clock.now()),
    )
    token = _SESSION.set(session)
    try:
        yield session
    finally:
        _SESSION.reset(token)


def current_session() -> LineageSession:
    session = _SESSION.get()
    if session is None:
        raise LineageNotConfigured("no active lineage session; wrap the run in lineage_session()")
    return session


@contextmanager
def derive(
    operation: Operation,
    *,
    output: OutputSpec,
    params: Mapping[str, Any],
    inputs: Sequence[InputRef] = (),
    rules: Sequence[str] = (),
    model_id: str | None = None,
    ttl_class: TtlClass = "permanent",
    determinism_class: DeterminismClass = "D1",
) -> Iterator[DerivationContext]:
    """Record one derivation. Nested calls auto-link parent←child through a contextvar.

    Commits on success; on exception records status='failed' and re-raises.
    """
    session = current_session()
    context = DerivationContext(
        operation=operation,
        output=output,
        params=params,
        model_id=model_id,
        ttl_class=ttl_class,
        determinism_class=determinism_class,
    )
    for ref in inputs:
        context.add_input(ref)
    for rule_id in rules:
        context.add_rule(rule_id)

    started_at = session.clock.now()
    parent_token = _PARENT.set(context)
    status: DerivationStatus = "ok"
    try:
        yield context
    except BaseException:
        status = "failed"
        raise
    finally:
        _PARENT.reset(parent_token)
        record = _build_record(context, session, started_at, status)
        context.derivation_id = record.derivation_id
        session.recorder.record(record)
        parent = _PARENT.get()
        if status == "ok" and parent is not None:
            parent.add_input(
                InputRef(
                    kind="derivation",
                    ref_id=record.derivation_id,
                    role="primary",
                    as_of_vintage=record.created_vintage,
                )
            )


def _build_record(
    context: DerivationContext,
    session: LineageSession,
    started_at: datetime,
    status: DerivationStatus,
) -> DerivationRecord:
    environment = session.environment
    finished_at = session.clock.now()
    identifier = derivation_id(
        operation=context.operation,
        inputs=context.inputs,
        params=context.params,
        code_version=environment.code_version,
        env_id=environment.env_id,
        rule_ids=[r.rule_id for r in context.rules],
        output=context.output,
    )
    return DerivationRecord(
        derivation_id=identifier,
        operation=context.operation,
        output_store=context.output.store,
        output_dataset=context.output.dataset,
        output_partition=dict(context.output.partition),
        output_locator=context.output.locator,
        output_sha256=context.output_sha256,
        output_rows=context.output_rows,
        output_schema_version=context.output.schema_version,
        params=dict(context.params),
        params_hash=hash_payload(context.params),
        code_version=environment.code_version,
        code_dirty=environment.code_dirty,
        env_id=environment.env_id,
        model_id=context.model_id,
        recipe_id=environment.recipe_id,
        created_vintage=context._knowledge_vintage(),
        created_at=started_at,
        duration_ms=int((finished_at - started_at).total_seconds() * 1000),
        correlation_id=session.correlation_id,
        status=status,
        determinism_class=context.determinism_class,
        ttl_class=context.ttl_class,
        inputs=context.inputs,
        rules=context.rules,
    )
