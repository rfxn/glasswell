"""Feature registry and well-time availability contracts (SB-02 §1)."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from glasswell.lineage.serialization import hash_payload

FeatureFamily = Literal["design", "location", "geology", "spacing", "operator", "vintage"]
KnowableAtRule = Literal[
    "permit_date", "spud_date", "completion_date", "first_production_month", "anchor"
]
MissingPolicy = Literal["native_nan", "indicator", "quarantine"]

_FEATURE_ID_RE = re.compile(r"\A[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*\Z")
_FEATURE_VERSION_RE = re.compile(r"\Afv(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\Z")


class FeatureLeakageError(ValueError):
    """A feature depends on an event after its subject well's anchor."""


class FeatureAvailabilityError(ValueError):
    """A feature's declared availability event is absent."""


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class FeatureSpec(Frozen):
    feature_id: str
    family: FeatureFamily
    dtype: str
    unit: str
    knowable_at_rule: KnowableAtRule
    publication_lag_days_p50: int = Field(ge=0)
    transform_id: str
    params: Mapping[str, Any] = Field(default_factory=dict)
    source_refs: tuple[str, ...]
    missing_policy: MissingPolicy
    member_of: tuple[str, ...]
    introduced_in_fv: str
    retired_in_fv: str | None = None

    @field_validator("feature_id")
    @classmethod
    def validate_feature_id(cls, value: str) -> str:
        if not _FEATURE_ID_RE.fullmatch(value):
            raise ValueError("feature_id must be a family-qualified stable slug")
        return value

    @field_validator("dtype", "unit", "transform_id")
    @classmethod
    def validate_nonempty_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be blank")
        return value

    @field_validator("source_refs", "member_of")
    @classmethod
    def validate_nonempty_unique_sequence(cls, value: Sequence[str]) -> tuple[str, ...]:
        normalized = tuple(value)
        if not normalized or any(not item.strip() for item in normalized):
            raise ValueError("sequence must contain nonblank values")
        if len(set(normalized)) != len(normalized):
            raise ValueError("sequence values must be unique")
        return tuple(sorted(normalized))

    @field_validator("introduced_in_fv", "retired_in_fv")
    @classmethod
    def validate_feature_version(cls, value: str | None) -> str | None:
        if value is not None and not _FEATURE_VERSION_RE.fullmatch(value):
            raise ValueError("feature versions use fv<MAJOR>.<MINOR>")
        return value

    @model_validator(mode="after")
    def validate_family_and_lifecycle(self) -> FeatureSpec:
        if self.feature_id.partition(".")[0] != self.family:
            raise ValueError("feature_id prefix must match family")
        if self.retired_in_fv is not None and _version_key(self.retired_in_fv) < _version_key(
            self.introduced_in_fv
        ):
            raise ValueError("retired_in_fv must not precede introduced_in_fv")
        return self


class FeatureEvents(Frozen):
    permit_date: date | None = None
    spud_date: date | None = None
    completion_date: date | None = None
    first_production_month: date | None = None
    anchor: date


class FeatureObservation(Frozen):
    api10: str
    feature_id: str
    value: Any
    knowable_at: date
    anchor: date


def _version_key(value: str) -> tuple[int, int]:
    match = _FEATURE_VERSION_RE.fullmatch(value)
    if match is None:
        raise ValueError(f"not a feature version: {value!r}")
    return int(match.group(1)), int(match.group(2))


def is_active(spec: FeatureSpec, feature_version: str) -> bool:
    version = _version_key(feature_version)
    return _version_key(spec.introduced_in_fv) <= version and (
        spec.retired_in_fv is None or version < _version_key(spec.retired_in_fv)
    )


def feature_set_hash(
    specs: Iterable[FeatureSpec], *, set_name: str, feature_version: str
) -> str:
    """Hash the latest active revision of every member in stable feature-id order."""
    target = _version_key(feature_version)
    latest: dict[str, FeatureSpec] = {}
    revisions: set[tuple[str, str]] = set()
    for spec in specs:
        revision = (spec.feature_id, spec.introduced_in_fv)
        if revision in revisions:
            raise ValueError(f"duplicate feature revision {revision!r}")
        revisions.add(revision)
        if _version_key(spec.introduced_in_fv) > target:
            continue
        current = latest.get(spec.feature_id)
        if current is None or _version_key(spec.introduced_in_fv) > _version_key(
            current.introduced_in_fv
        ):
            latest[spec.feature_id] = spec
    selected = sorted(
        (
            spec.model_dump(mode="json")
            for spec in latest.values()
            if set_name in spec.member_of and is_active(spec, feature_version)
        ),
        key=lambda row: row["feature_id"],
    )
    if not selected:
        raise ValueError(f"feature set {set_name!r} is empty at {feature_version}")
    return "sha256:" + hash_payload(selected)


def observe_feature(
    *, api10: str, spec: FeatureSpec, value: Any, events: FeatureEvents
) -> FeatureObservation:
    knowable_at = getattr(events, spec.knowable_at_rule)
    if knowable_at is None:
        raise FeatureAvailabilityError(
            f"{api10} lacks {spec.knowable_at_rule} required by {spec.feature_id}"
        )
    if knowable_at > events.anchor:
        raise FeatureLeakageError(
            f"{spec.feature_id} for {api10} is knowable at {knowable_at}, after anchor "
            f"{events.anchor}"
        )
    return FeatureObservation(
        api10=api10,
        feature_id=spec.feature_id,
        value=value,
        knowable_at=knowable_at,
        anchor=events.anchor,
    )
