from __future__ import annotations


class LineageError(Exception):
    """Base class for every spine-raised error."""


class LineageNotConfigured(LineageError):
    """derive() or emit() was called outside an active lineage session."""


class InvalidHandle(LineageError):
    pass


class InvalidSelector(LineageError):
    pass


class UnknownAuditEvent(LineageError):
    pass


class UnknownRuleKind(LineageError):
    pass


class RuleSpecError(LineageError):
    """A conformance rule row is malformed for its declared kind."""


class DeterminismViolation(LineageError):
    """SB-07 §1.3: an identical derivation spec produced different output bytes."""

    def __init__(self, derivation_id: str, recorded_sha256: str, observed_sha256: str) -> None:
        super().__init__(
            f"{derivation_id}: recorded output sha256 {recorded_sha256} "
            f"but this run produced {observed_sha256}"
        )
        self.derivation_id = derivation_id
        self.recorded_sha256 = recorded_sha256
        self.observed_sha256 = observed_sha256


class ManifestConflict(LineageError):
    """The same bytes were registered under a different source slot."""
