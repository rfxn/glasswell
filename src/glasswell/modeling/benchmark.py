"""Strict, content-addressed benchmark artifact contract (SB-02 §7.4)."""

from __future__ import annotations

import base64
import hashlib
from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from glasswell.lineage.serialization import canonical_json

SLICE_MIN_N = 50
Verdict = Literal["ml_better", "tie", "control_better"]
ResultStatus = Literal["ok", "insufficient_n"]


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)


class BenchmarkArm(Frozen):
    arm: str
    model_ids: Mapping[str, str] = Field(default_factory=dict)
    type_curve_spec: Mapping[str, Any] = Field(default_factory=dict)
    spec: Mapping[str, Any] = Field(default_factory=dict)


class BenchmarkPopulation(Frozen):
    n_train: int = Field(ge=0)
    n_cal: int = Field(ge=0)
    n_test: int = Field(ge=0)
    n_reassigned_by_group_rule: int = Field(ge=0)
    censored_share: float = Field(ge=0, le=1)
    withheld_share: float = Field(ge=0, le=1)
    late_report_share: float = Field(ge=0, le=1)
    control_unavailable_share: float = Field(ge=0, le=1)


class BenchmarkSlice(Frozen):
    dim: str
    value: str | None = None


class PinballMetrics(Frozen):
    p10: float
    p50: float
    p90: float


class CoverageMetrics(Frozen):
    central: float = Field(ge=0, le=1)
    lower_tail: float = Field(ge=0, le=1)
    upper_tail: float = Field(ge=0, le=1)
    ci_lo: float = Field(ge=0, le=1)
    ci_hi: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_interval(self) -> CoverageMetrics:
        if self.ci_lo > self.ci_hi:
            raise ValueError("coverage ci_lo must not exceed ci_hi")
        return self


class ArmMetrics(Frozen):
    interval_score: float
    pinball: PinballMetrics
    coverage: CoverageMetrics
    sharpness_bbl: float
    mae_bbl: float
    medape: float
    bias_bbl: float


class MlAdvantage(Frozen):
    metric: str
    delta: float
    delta_pct: float
    ci_lo: float
    ci_hi: float
    verdict: Verdict

    @model_validator(mode="after")
    def validate_derived_verdict(self) -> MlAdvantage:
        if self.ci_lo > self.ci_hi:
            raise ValueError("ml advantage ci_lo must not exceed ci_hi")
        expected = verdict_from_ci(self.ci_lo, self.ci_hi)
        if self.verdict != expected:
            raise ValueError(f"verdict must be derived from CI as {expected}")
        return self


class BenchmarkResult(Frozen):
    stream: str
    horizon: int = Field(gt=0)
    slice: BenchmarkSlice
    n: int = Field(ge=0)
    status: ResultStatus
    by_arm: Mapping[str, ArmMetrics] = Field(default_factory=dict)
    ml_advantage: MlAdvantage | None = None

    @model_validator(mode="after")
    def validate_sample_status(self) -> BenchmarkResult:
        expected: ResultStatus = "insufficient_n" if self.n < SLICE_MIN_N else "ok"
        if self.status != expected:
            raise ValueError(f"status must be {expected} for n={self.n}")
        if expected == "ok" and self.ml_advantage is None:
            raise ValueError("results with sufficient n require ml_advantage")
        return self


class LosingSlice(Frozen):
    stream: str
    horizon: int
    dim: str
    value: str | None
    n: int
    delta: float
    ci_lo: float
    ci_hi: float


class BenchmarkArtifact(Frozen):
    benchmark_id: str = Field(pattern=r"^bmk_[a-z0-9]+$")
    recipe_id: str = Field(pattern=r"^rcp_[a-z0-9_]+$")
    derivation_id: str = Field(pattern=r"^drv_[a-z0-9_]+$")
    basin: str
    origin: str = Field(pattern=r"^[0-9]{4}-(0[1-9]|1[0-2])$")
    split_id: str = Field(pattern=r"^spl_[a-z0-9_]+$")
    knowledge_cutoff: date
    eval_vintage: date
    feature_version: str = Field(pattern=r"^fv(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
    feature_set_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    arms: tuple[BenchmarkArm, ...] = Field(min_length=1)
    population: BenchmarkPopulation
    results: tuple[BenchmarkResult, ...] = Field(min_length=1)
    slices_where_ml_loses: tuple[LosingSlice, ...]
    reader_summary: str
    plausibility_flags: tuple[str, ...]

    @model_validator(mode="after")
    def validate_generated_fields(self) -> BenchmarkArtifact:
        if self.eval_vintage < self.knowledge_cutoff:
            raise ValueError("eval_vintage must not precede knowledge_cutoff")
        arm_names = [arm.arm for arm in self.arms]
        if len(set(arm_names)) != len(arm_names):
            raise ValueError("benchmark arm names must be unique")
        expected_arms = set(arm_names)
        for result in self.results:
            if result.status == "ok" and set(result.by_arm) != expected_arms:
                raise ValueError("every sufficient result requires metrics for every arm")
        losing = losing_slices_from_results(self.results)
        if tuple(self.slices_where_ml_loses) != losing:
            raise ValueError("slices_where_ml_loses must be generated from results")
        expected_flags = plausibility_flags(losing)
        if tuple(self.plausibility_flags) != expected_flags:
            raise ValueError("plausibility_flags must be generated from results")
        expected_summary = reader_summary(self.results, losing)
        if self.reader_summary != expected_summary:
            raise ValueError("reader_summary must be generated from results")
        payload = self.model_dump(mode="json", exclude={"benchmark_id"})
        if self.benchmark_id != _content_id("bmk_", payload):
            raise ValueError("benchmark_id does not match artifact content")
        return self


def verdict_from_ci(ci_lo: float, ci_hi: float) -> Verdict:
    if ci_hi < 0:
        return "ml_better"
    if ci_lo > 0:
        return "control_better"
    return "tie"


def losing_slices_from_results(results: Sequence[BenchmarkResult]) -> tuple[LosingSlice, ...]:
    losing = []
    for result in results:
        advantage = result.ml_advantage
        if advantage is None or advantage.verdict != "control_better":
            continue
        losing.append(
            LosingSlice(
                stream=result.stream,
                horizon=result.horizon,
                dim=result.slice.dim,
                value=result.slice.value,
                n=result.n,
                delta=advantage.delta,
                ci_lo=advantage.ci_lo,
                ci_hi=advantage.ci_hi,
            )
        )
    return tuple(
        sorted(losing, key=lambda item: (item.stream, item.horizon, item.dim, item.value or ""))
    )


def plausibility_flags(losing: Sequence[LosingSlice]) -> tuple[str, ...]:
    return () if losing else ("no_losing_slices",)


def reader_summary(
    results: Sequence[BenchmarkResult], losing: Sequence[LosingSlice]
) -> str:
    sufficient = [result for result in results if result.status == "ok"]
    insufficient = len(results) - len(sufficient)
    if losing:
        worst = max(losing, key=lambda item: (item.ci_lo, item.delta))
        outcome = (
            f"ML loses most clearly on {worst.stream} h{worst.horizon} "
            f"{worst.dim}={worst.value or 'all'} (n={worst.n}, delta={worst.delta:.6g}, "
            f"95% CI [{worst.ci_lo:.6g}, {worst.ci_hi:.6g}])."
        )
    else:
        outcome = "No reported slice has a confidence interval wholly favoring a control."
    return (
        f"{outcome} {len(sufficient)} slices have sufficient n; "
        f"{insufficient} are reported as insufficient_n."
    )


def _content_id(prefix: str, payload: object) -> str:
    digest = hashlib.sha256(canonical_json(payload)).digest()[:12]
    encoded = base64.b32encode(digest).decode("ascii").rstrip("=").lower()
    return prefix + encoded


def _json_value(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, Mapping):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def build_benchmark_artifact(**values: Any) -> BenchmarkArtifact:
    """Construct the artifact while deriving every honesty-sensitive field."""
    results = tuple(BenchmarkResult.model_validate(item) for item in values.pop("results"))
    arms = tuple(BenchmarkArm.model_validate(item) for item in values.pop("arms"))
    population = BenchmarkPopulation.model_validate(values.pop("population"))
    losing = losing_slices_from_results(results)
    generated = {
        **values,
        "arms": arms,
        "population": population,
        "results": results,
        "slices_where_ml_loses": losing,
        "reader_summary": reader_summary(results, losing),
        "plausibility_flags": plausibility_flags(losing),
    }
    generated["benchmark_id"] = _content_id("bmk_", _json_value(generated))
    return BenchmarkArtifact.model_validate(generated)
