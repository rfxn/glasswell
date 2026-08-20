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
from glasswell.lineage.errors import (
    DeterminismViolation,
    InvalidHandle,
    InvalidSelector,
    LineageError,
    LineageNotConfigured,
    RuleSpecError,
    UnknownAuditEvent,
    UnknownRuleKind,
)
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
from glasswell.lineage.store import PostgresRecorder
from glasswell.lineage.vintages import open_vintage, select_production

__all__ = [
    "AuditEvent",
    "ConformanceRule",
    "DerivationContext",
    "DerivationRecord",
    "DeriveEnvironment",
    "DeterminismViolation",
    "Handle",
    "InputRef",
    "InvalidHandle",
    "InvalidSelector",
    "LineageError",
    "LineageNotConfigured",
    "LineageSession",
    "ManifestRecord",
    "ManifestRegistration",
    "OutputSpec",
    "PostgresRecorder",
    "QuarantineBatch",
    "QuarantineResult",
    "RuleApplication",
    "RuleRef",
    "RuleSpecError",
    "UnknownAuditEvent",
    "UnknownRuleKind",
    "VintageRecord",
    "apply_registry_rules",
    "apply_rules",
    "current_session",
    "derivation_id",
    "derive",
    "emit",
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
    "select_production",
]
