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
    """The same bytes were registered under a different source slot.

    `lineage.manifests.sha256` is unique, so bytes have exactly one owning slot and a second
    claimant cannot be represented. Returning the incumbent instead would bind the claimant's
    derivations to the incumbent's provenance, and `/explain` would resolve them — to the wrong
    government file. Refusal is the only answer that keeps a handle honest.
    """

    def __init__(
        self, sha256: str, owner: tuple[str, str], claimant: tuple[str, str], bytes_: int
    ) -> None:
        super().__init__(
            f"sha256 {sha256} is already registered to {owner[0]}/{owner[1]};"
            f" {claimant[0]}/{claimant[1]} cannot claim the same {bytes_} byte(s)"
        )
        self.sha256 = sha256
        self.owner = owner
        self.claimant = claimant


class VintageAlreadyPromoted(LineageError):
    """DIR-2 at the canonical grain: this vintage already answers, and differently.

    The store-side analogue of DeterminismViolation (SB-07 §1.3). Knowledge time is a date, so
    two promotions on one calendar day share a primary key; re-running one is a no-op only when
    it computes what is already there. Anything else would have to rewrite a vintage, which a
    re-promotion never does — it appends one.
    """

    def __init__(self, dataset: str, report_vintage: object, rows: int, example: str) -> None:
        super().__init__(
            f"{dataset}: report_vintage {report_vintage} already holds {rows} row(s) that"
            f" differ from what this run computed (first: {example}). A re-promotion appends a"
            " vintage and never rewrites one, and knowledge time is a date, so this run must"
            " open a later one — re-run on a day after the newest report_vintage."
        )
        self.dataset = dataset
        self.report_vintage = report_vintage
        self.rows = rows
        self.example = example


UNRESOLVED_REASONS = (
    "selector_ambiguous",
    "depth_exceeded",
    "derivation_swept",
    "unknown_id",
)


class LineageUnresolved(LineageError):
    """SB-07 §9.5: an auditor never gets a bare 404 — the error says where resolution stopped."""

    code = "lineage_unresolved"

    def __init__(self, handle: str, *, reason: str, last_resolved: str | None = None) -> None:
        super().__init__(
            f"{handle}: resolution stopped ({reason}); "
            f"last resolvable node {last_resolved or 'none'}"
        )
        self.handle = handle
        self.reason = reason
        self.last_resolved = last_resolved
