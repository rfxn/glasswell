"""The first versioned feature declaration (SB-02 §1.5)."""

from __future__ import annotations

import psycopg
from psycopg.types.json import Jsonb

from glasswell.modeling.features import FeatureSpec

FEATURE_VERSION = "fv1.0"

FEATURE_SPECS: tuple[FeatureSpec, ...] = (
    FeatureSpec(
        feature_id="geology.formation_group",
        family="geology",
        dtype="categorical",
        unit="category",
        knowable_at_rule="completion_date",
        publication_lag_days_p50=0,
        transform_id="lookup_formation_alias",
        params={
            "alias_table": "lineage.formation_aliases",
            "min_confidence": "0.800",
            "reported_pool_field": "pool_reported",
            "source_id": "nd_mpr_xlsx",
        },
        source_refs=(
            "canonical.well_completions.pool_reported",
            "lineage.formation_aliases",
        ),
        missing_policy="native_nan",
        member_of=("full", "rock_location_only", "design_adjusted", "no_depletion"),
        introduced_in_fv=FEATURE_VERSION,
    ),
)

_INSERT = """
insert into features.feature_specs
    (feature_id, family, dtype, unit, knowable_at_rule, publication_lag_days_p50,
     transform_id, params, source_refs, missing_policy, member_of, introduced_in_fv,
     retired_in_fv)
values
    (%(feature_id)s, %(family)s, %(dtype)s, %(unit)s, %(knowable_at_rule)s,
     %(publication_lag_days_p50)s, %(transform_id)s, %(params)s, %(source_refs)s,
     %(missing_policy)s, %(member_of)s, %(introduced_in_fv)s, %(retired_in_fv)s)
on conflict (feature_id, introduced_in_fv) do nothing
"""


def seed_features(connection: psycopg.Connection) -> int:
    with connection.cursor() as cursor:
        cursor.executemany(
            _INSERT,
            [
                {
                    **spec.model_dump(),
                    "params": Jsonb(dict(spec.params)),
                    "source_refs": list(spec.source_refs),
                    "member_of": list(spec.member_of),
                }
                for spec in FEATURE_SPECS
            ],
        )
        cursor.execute("select count(*) from features.feature_specs")
        return int(cursor.fetchone()[0])
