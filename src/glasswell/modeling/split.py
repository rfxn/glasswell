"""Temporal holdout and pad-group leakage guard (SB-02 §3)."""

from __future__ import annotations

import base64
import hashlib
import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from glasswell.lineage.serialization import canonical_json

CAL_WINDOW_MONTHS = 12
EMBARGO_MONTHS = 0
PAD_RADIUS_M = 150.0
PAD_WINDOW_DAYS = 180
PAD_GROUP_MAX_SHARE = 0.02
PAD_CRS_EPSG = 5070

Partition = Literal["train", "cal", "test"]


class PadGroupChainingError(ValueError):
    """A connected component is too large to represent one pad."""


class SplitDefinitionError(ValueError):
    """A temporal split cannot be constructed from the supplied population."""


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)


class WellTimeline(Frozen):
    api10: str
    first_production_month: date
    completion_date: date
    label_completeness_date: date
    surface_x_m: float | None = None
    surface_y_m: float | None = None
    spacing_unit_id: str | None = None

    @field_validator("first_production_month")
    @classmethod
    def require_month_start(cls, value: date) -> date:
        if value.day != 1:
            raise ValueError("first_production_month must be the first day of a month")
        return value

    @model_validator(mode="after")
    def require_coordinate_pair(self) -> WellTimeline:
        if (self.surface_x_m is None) != (self.surface_y_m is None):
            raise ValueError("surface coordinates must be supplied as an x/y pair")
        return self


class PadGroupStats(Frozen):
    component_size_max: int
    component_size_p99: int
    component_size_mean: float
    pad_group_max_share: float


class HoldoutDefinition(Frozen):
    boundary: date
    knowledge_cutoff: date
    calibration_window_months: int = CAL_WINDOW_MONTHS
    embargo_months: int = EMBARGO_MONTHS
    pad_radius_m: float = PAD_RADIUS_M
    pad_window_days: int = PAD_WINDOW_DAYS
    pad_crs_epsg: int = PAD_CRS_EPSG
    pad_group_max_share_limit: float = PAD_GROUP_MAX_SHARE
    reporting_lags: Mapping[str, int] = Field(default_factory=dict)

    @field_validator("reporting_lags")
    @classmethod
    def require_nonnegative_reporting_lags(cls, value: Mapping[str, int]) -> Mapping[str, int]:
        if any(not source.strip() or days < 0 for source, days in value.items()):
            raise ValueError("reporting lags require nonblank sources and nonnegative days")
        return value


class SplitAssignment(Frozen):
    api10: str
    pad_group_id: str
    partition: Partition
    ungrouped_partition: Partition


class SplitObject(Frozen):
    split_id: str
    basin: str
    origin: date
    horizon_months: int
    holdout_def: HoldoutDefinition
    assignments: tuple[SplitAssignment, ...]
    n_wells_reassigned_by_group_rule: int
    pad_group_stats: PadGroupStats
    plausibility_flags: tuple[str, ...] = ()


class _DisjointSet:
    def __init__(self, keys: Sequence[str]) -> None:
        self.parent = {key: key for key in keys}

    def find(self, key: str) -> str:
        parent = self.parent[key]
        if parent != key:
            self.parent[key] = self.find(parent)
        return self.parent[key]

    def union(self, left: str, right: str) -> None:
        left_root, right_root = self.find(left), self.find(right)
        if left_root == right_root:
            return
        lower, upper = sorted((left_root, right_root))
        self.parent[upper] = lower


def _content_id(prefix: str, payload: object) -> str:
    digest = hashlib.sha256(canonical_json(payload)).digest()[:12]
    encoded = base64.b32encode(digest).decode("ascii").rstrip("=").lower()
    return prefix + encoded


def _half_year(value: date) -> str:
    return f"{value.year}-h{1 if value.month <= 6 else 2}"


def _group_id(api10s: Sequence[str]) -> str:
    return _content_id("pad_", sorted(api10s))


def build_pad_groups(
    wells: Sequence[WellTimeline],
    *,
    radius_m: float = PAD_RADIUS_M,
    window_days: int = PAD_WINDOW_DAYS,
) -> Mapping[str, str]:
    """Build deterministic single-linkage components in already-projected EPSG:5070 metres."""
    if radius_m <= 0 or window_days < 0:
        raise ValueError("pad radius must be positive and window days nonnegative")
    by_api = {well.api10: well for well in wells}
    if len(by_api) != len(wells):
        raise SplitDefinitionError("api10 values must be unique")

    disjoint = _DisjointSet(sorted(by_api))
    cell_size = radius_m
    cells: dict[tuple[int, int], list[WellTimeline]] = defaultdict(list)
    projected = [well for well in wells if well.surface_x_m is not None]
    for well in sorted(projected, key=lambda item: item.api10):
        assert well.surface_x_m is not None
        assert well.surface_y_m is not None
        cell = (math.floor(well.surface_x_m / cell_size), math.floor(well.surface_y_m / cell_size))
        for x_offset in (-1, 0, 1):
            for y_offset in (-1, 0, 1):
                for other in cells.get((cell[0] + x_offset, cell[1] + y_offset), ()):
                    assert other.surface_x_m is not None
                    assert other.surface_y_m is not None
                    distance = math.hypot(
                        well.surface_x_m - other.surface_x_m,
                        well.surface_y_m - other.surface_y_m,
                    )
                    completion_gap = abs((well.completion_date - other.completion_date).days)
                    if distance <= radius_m and completion_gap <= window_days:
                        disjoint.union(well.api10, other.api10)
        cells[cell].append(well)

    fallback: dict[tuple[str, str], list[str]] = defaultdict(list)
    for well in wells:
        if well.surface_x_m is None and well.spacing_unit_id is not None:
            fallback[(well.spacing_unit_id, _half_year(well.completion_date))].append(well.api10)
    for members in fallback.values():
        for api10 in members[1:]:
            disjoint.union(members[0], api10)

    components: dict[str, list[str]] = defaultdict(list)
    for api10 in sorted(by_api):
        components[disjoint.find(api10)].append(api10)
    return {
        api10: _group_id(members)
        for members in components.values()
        for api10 in members
    }


def _shift_months(value: date, months: int) -> date:
    month_index = value.year * 12 + value.month - 1 + months
    year, zero_based_month = divmod(month_index, 12)
    return date(year, zero_based_month + 1, 1)


def _partition(value: date, boundary: date, calibration_start: date) -> Partition:
    if value < calibration_start:
        return "train"
    if value < boundary:
        return "cal"
    return "test"


def _median_date(values: Sequence[date]) -> date:
    ordinals = sorted(value.toordinal() for value in values)
    middle = len(ordinals) // 2
    if len(ordinals) % 2:
        ordinal = ordinals[middle]
    else:
        ordinal = (ordinals[middle - 1] + ordinals[middle]) // 2
    return date.fromordinal(ordinal)


def _pad_group_stats(group_sizes: Sequence[int], population: int) -> PadGroupStats:
    ordered = sorted(group_sizes)
    p99_index = max(0, math.ceil(0.99 * len(ordered)) - 1)
    maximum = ordered[-1]
    return PadGroupStats(
        component_size_max=maximum,
        component_size_p99=ordered[p99_index],
        component_size_mean=sum(ordered) / len(ordered),
        pad_group_max_share=maximum / population,
    )


def build_temporal_split(
    wells: Sequence[WellTimeline],
    *,
    basin: str,
    boundary: date,
    horizon_months: int,
    reporting_lags: Mapping[str, int],
) -> SplitObject:
    if not wells:
        raise SplitDefinitionError("split population is empty")
    if boundary.day != 1:
        raise SplitDefinitionError("boundary must be the first day of a month")
    if horizon_months <= 0:
        raise SplitDefinitionError("horizon_months must be positive")

    calibration_start = _shift_months(boundary, -CAL_WINDOW_MONTHS)
    group_by_api = build_pad_groups(wells)
    members_by_group: dict[str, list[WellTimeline]] = defaultdict(list)
    for well in wells:
        members_by_group[group_by_api[well.api10]].append(well)

    stats = _pad_group_stats([len(members) for members in members_by_group.values()], len(wells))
    if stats.pad_group_max_share > PAD_GROUP_MAX_SHARE:
        raise PadGroupChainingError(
            f"largest pad group share {stats.pad_group_max_share:.6f} exceeds "
            f"{PAD_GROUP_MAX_SHARE:.6f}"
        )

    assignments: list[SplitAssignment] = []
    for group_id, members in sorted(members_by_group.items()):
        grouped_partition = _partition(
            _median_date([well.first_production_month for well in members]),
            boundary,
            calibration_start,
        )
        for well in members:
            assignments.append(
                SplitAssignment(
                    api10=well.api10,
                    pad_group_id=group_id,
                    partition=grouped_partition,
                    ungrouped_partition=_partition(
                        well.first_production_month, boundary, calibration_start
                    ),
                )
            )
    assignments.sort(key=lambda item: item.api10)
    reassigned = sum(
        assignment.partition != assignment.ungrouped_partition for assignment in assignments
    )
    training_api10s = {
        assignment.api10 for assignment in assignments if assignment.partition != "test"
    }
    knowledge_dates = [
        well.label_completeness_date for well in wells if well.api10 in training_api10s
    ]
    if not knowledge_dates:
        raise SplitDefinitionError("TRAIN and CAL are both empty")
    knowledge_cutoff = max(knowledge_dates)
    holdout = HoldoutDefinition(
        boundary=boundary,
        knowledge_cutoff=knowledge_cutoff,
        reporting_lags=dict(sorted(reporting_lags.items())),
    )
    flags = ("zero_pad_group_reassignments",) if reassigned == 0 else ()
    payload = {
        "basin": basin,
        "origin": boundary,
        "horizon_months": horizon_months,
        "holdout_def": holdout.model_dump(mode="json"),
        "assignments": [assignment.model_dump(mode="json") for assignment in assignments],
        "n_wells_reassigned_by_group_rule": reassigned,
        "pad_group_stats": stats.model_dump(mode="json"),
        "plausibility_flags": flags,
    }
    return SplitObject(
        split_id=_content_id("spl_", payload),
        basin=basin,
        origin=boundary,
        horizon_months=horizon_months,
        holdout_def=holdout,
        assignments=tuple(assignments),
        n_wells_reassigned_by_group_rule=reassigned,
        pad_group_stats=stats,
        plausibility_flags=flags,
    )
