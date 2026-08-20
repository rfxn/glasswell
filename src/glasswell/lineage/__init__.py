"""The lineage and reproducibility spine (SB-07).

Everything that produces or serves a figure imports this package. A second derivation
writer anywhere in the tree is a review failure.
"""

from glasswell.lineage.audit import emit
from glasswell.lineage.capture import (
    DerivationContext,
    LineageSession,
    current_session,
    derive,
    lineage_session,
)
from glasswell.lineage.conformance import (
    QuarantineBatch,
    RuleApplication,
    apply_registry_rules,
    apply_rules,
    load_rules,
)
from glasswell.lineage.envelope import (
    Envelope,
    Figure,
    Series,
    attach_lineage,
    figure,
    series,
)
from glasswell.lineage.errors import (
    DeterminismViolation,
    InvalidHandle,
    InvalidSelector,
    LineageError,
    LineageNotConfigured,
    LineageUnresolved,
    RuleSpecError,
    UnknownAuditEvent,
    UnknownRuleKind,
)
from glasswell.lineage.explain import Chain, resolve_chain, resolve_chains, to_json
from glasswell.lineage.fetch import FetchResult, fetch_raw
from glasswell.lineage.ids import (
    Handle,
    derivation_id,
    format_handle,
    format_selector,
    manifest_id,
    new_ulid,
    parse_handle,
    parse_selector,
)
from glasswell.lineage.manifests import ManifestRegistration, manifest_chain, register_manifest
from glasswell.lineage.models import (
    AuditEvent,
    ConformanceRule,
    DerivationRecord,
    DeriveEnvironment,
    InputRef,
    ManifestRecord,
    OutputSpec,
    RuleRef,
    VintageRecord,
)
from glasswell.lineage.quarantine import QuarantineResult, quarantine
from glasswell.lineage.recipes import build_recipe
from glasswell.lineage.store import PostgresRecorder
from glasswell.lineage.vintages import open_vintage, select_production

__all__ = [
    "AuditEvent",
    "Chain",
    "ConformanceRule",
    "DerivationContext",
    "DerivationRecord",
    "DeriveEnvironment",
    "DeterminismViolation",
    "Envelope",
    "FetchResult",
    "Figure",
    "Handle",
    "InputRef",
    "InvalidHandle",
    "InvalidSelector",
    "LineageError",
    "LineageNotConfigured",
    "LineageSession",
    "LineageUnresolved",
    "ManifestRecord",
    "ManifestRegistration",
    "OutputSpec",
    "PostgresRecorder",
    "QuarantineBatch",
    "QuarantineResult",
    "RuleApplication",
    "RuleRef",
    "RuleSpecError",
    "Series",
    "UnknownAuditEvent",
    "UnknownRuleKind",
    "VintageRecord",
    "apply_registry_rules",
    "apply_rules",
    "attach_lineage",
    "build_recipe",
    "current_session",
    "derivation_id",
    "derive",
    "emit",
    "fetch_raw",
    "figure",
    "format_handle",
    "format_selector",
    "lineage_session",
    "load_rules",
    "manifest_chain",
    "manifest_id",
    "new_ulid",
    "open_vintage",
    "parse_handle",
    "parse_selector",
    "quarantine",
    "register_manifest",
    "resolve_chain",
    "resolve_chains",
    "select_production",
    "series",
    "to_json",
]
