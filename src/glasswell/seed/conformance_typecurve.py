"""The type-curve serving decisions, as rows (R8). No router decides any of this for itself.

Which pinned publication a figure may be served from, which ladder rung produced it, what
`typecurve_per_kft` rescales to, which quantile convention is in force, and whether an
unavailable control is a value or an absence — five decisions that shape every served type
curve. Three were compiled into `tcv1.0` when it was built; two are serving decisions this
release makes. All five are `code_ref`: a rule row for `nd_mpr_xlsx` at stage `conform` is
loaded by the ND promote path, so a non-`code_ref` kind would have to be executable there.
"""

from __future__ import annotations

from datetime import date

import psycopg
from psycopg.types.json import Jsonb

from glasswell.seed.conformance_nd import MPR_INDEX_URL

# The commit that introduced type_curve.py, QUANTILE_CONVENTION and tcv1.0 (2a855ca): the day
# the three build-time decisions took effect, which is not the day glasswell published them.
CONTROL_BUILT_FROM = date(2026, 8, 26)
# The day the control became a served surface and the two serving decisions took effect.
SERVING_FROM = date(2026, 8, 30)

LADDER_EXECUTOR = "glasswell.modeling.type_curve:resolve_fallback"
NORMALIZATION_EXECUTOR = "glasswell.modeling.type_curve:aggregate_peer_curves"
QUANTILE_EXECUTOR = "glasswell.modeling.type_curve:empirical_quantiles"
PUBLICATION_EXECUTOR = "glasswell.modeling.served:resolve_pinned_control"
UNAVAILABLE_EXECUTOR = "glasswell.api.routers.type_curves:get_well_type_curve"

TYPECURVE_RULES: tuple[dict[str, object], ...] = (
    {
        "rule_id": "cr_tc_publication_scope_1",
        "source_id": "nd_mpr_xlsx",
        "stage": "conform",
        "rule_kind": "code_ref",
        "applies_to_fields": ["control_derivation_id"],
        "spec": {
            "module_function": PUBLICATION_EXECUTOR,
            "version": "1",
            "contract_note": (
                "returns the single accepted publication a served figure may read, resolved"
                " from lineage.p3_publication_receipts and never from the artifact tree"
            ),
            "selection": "greatest_eval_vintage_then_publication_id",
            "override_parameter": "publication",
            "agreements": [
                "accepted_publication_receipt",
                "registered_typecurve_build_derivation",
                "receipt_and_derivation_name_the_same_bytes",
                "contained_non_symlink_path_whose_digest_matches_output_sha256",
            ],
        },
        "code_ref": PUBLICATION_EXECUTOR,
        "rule": (
            "Only an accepted P3 publication receipt names a servable control artifact; latest"
            " on disk is not a policy."
        ),
        "rationale": (
            "The pin is not unique on disk and cannot be recovered by scanning. The database"
            " holds two typecurve.build derivations for modeling.typecurve_control and ten"
            " features.build derivations, one of them still registered against a /tmp path"
            " from a review run. Resolving by output_dataset, by locator or by latest would"
            " each pick a different artifact, and none of them is the one the P3 gate"
            " accepted. A policy statement rather than a mapping, so it is recorded as the"
            " kind SB-07 §6.1 provides for exactly that; the executor named in the spec is"
            " the resolver every served type-curve figure passes through."
        ),
        "evidence_url": MPR_INDEX_URL,
        "effective_from": SERVING_FROM,
    },
    {
        "rule_id": "cr_tc_peer_ladder_1",
        "source_id": "nd_mpr_xlsx",
        "stage": "conform",
        "rule_kind": "code_ref",
        "applies_to_fields": ["fallback_level", "peer_set_id", "peer_count"],
        "spec": {
            "module_function": LADDER_EXECUTOR,
            "version": "1",
            "contract_note": (
                "returns the first ladder rung with at least min_peers eligible peers, or"
                " control_unavailable; the served fallback_level is that rung and is the peer"
                " assumption in force for the row"
            ),
            "ladder": [
                "formation_area_length",
                "formation_area",
                "formation_basin",
                "control_unavailable",
            ],
            "min_peers": 20,
            "vintage_window_months": 36,
            "peer_population": "TRAIN_union_CAL_only",
            "pad_mates": "excluded",
        },
        "code_ref": LADDER_EXECUTOR,
        "rule": (
            "A control quantile comes from the first rung of a closed four-step ladder that"
            " has twenty eligible peers inside a thirty-six-month vintage window, with pad"
            " mates excluded and peers drawn only from the training and calibration arms."
        ),
        "rationale": (
            "Protocol 4D: a rollup states the assumption in force, and for a type curve the"
            " peer assumption is the rung. Two subjects on the same page can carry the same"
            " column name and different peer definitions, so a reader who is not told the rung"
            " is reading two incomparable numbers as one. Compiled into tcv1.0 on"
            " 2026-08-26 and recorded as code_ref because the executor is the build module the"
            " spec names, not a mapping this registry can apply."
        ),
        "evidence_url": MPR_INDEX_URL,
        "effective_from": CONTROL_BUILT_FROM,
    },
    {
        "rule_id": "cr_tc_normalization_1",
        "source_id": "nd_mpr_xlsx",
        "stage": "conform",
        "rule_kind": "code_ref",
        "applies_to_fields": ["normalization", "subject_lateral_length_ft"],
        "spec": {
            "module_function": NORMALIZATION_EXECUTOR,
            "version": "1",
            "contract_note": (
                "returns per-kft peer quantiles; the served typecurve_per_kft arm multiplies"
                " them by the subject's own lateral length in thousands of feet, so it is a"
                " length-adjusted volume and not a rate per thousand feet"
            ),
            "arms": ["typecurve_absolute", "typecurve_per_kft"],
            "per_kft_rescale": "peer_quantile_per_1000ft * subject_lateral_length_ft / 1000",
        },
        "code_ref": NORMALIZATION_EXECUTOR,
        "rule": (
            "typecurve_per_kft is the peer quantile per thousand lateral feet rescaled to the"
            " subject's own lateral length, not a raw per-thousand-feet number."
        ),
        "rationale": (
            "The name says per-kft and the value is not per-kft: the peer quantile is taken"
            " per thousand feet so that peers of different lengths are comparable, then"
            " multiplied back by the subject's length so the served figure is in the subject's"
            " own units. A reader who takes the arm at its name is off by the subject's"
            " lateral length in kft, which on the Bakken is a factor of about ten. Compiled"
            " into tcv1.0 on 2026-08-26; recorded as code_ref because the executor is the"
            " aggregation the spec names."
        ),
        "evidence_url": MPR_INDEX_URL,
        "effective_from": CONTROL_BUILT_FROM,
    },
    {
        "rule_id": "cr_tc_quantile_convention_1",
        "source_id": "nd_mpr_xlsx",
        "stage": "conform",
        "rule_kind": "code_ref",
        "applies_to_fields": [
            "quantile_convention",
            "monthly_p10",
            "monthly_p50",
            "monthly_p90",
        ],
        "spec": {
            "module_function": QUANTILE_EXECUTOR,
            "version": "1",
            "contract_note": (
                "returns p10 < p50 < p90 by ascending value; p10 is the low case, which is the"
                " opposite of the reserves convention in which P10 is the high case"
            ),
            "convention": "statistical_ascending",
            "not_the_reserves_convention": True,
            "interpolation": "percentile_cont_linear_over_equal_weight_observations",
        },
        "code_ref": QUANTILE_EXECUTOR,
        "rule": (
            "Served quantiles are statistical-ascending: p10 is the low case and p90 the high"
            " case."
        ),
        "rationale": (
            "In the reserves convention a reader of this industry knows, P10 is the high case"
            " and P90 the low one — exactly inverted from what glasswell serves. Publishing"
            " P10/P50/P90 without naming the convention is the naked claim this project exists"
            " to prevent, and it is a claim that reverses the reader's conclusion rather than"
            " blurring it. Compiled into tcv1.0 on 2026-08-26 as QUANTILE_CONVENTION and"
            " served on every row; recorded as code_ref because the executor is the quantile"
            " function the spec names."
        ),
        "evidence_url": MPR_INDEX_URL,
        "effective_from": CONTROL_BUILT_FROM,
    },
    {
        "rule_id": "cr_tc_unavailable_vocab_1",
        "source_id": "nd_mpr_xlsx",
        "stage": "conform",
        "rule_kind": "code_ref",
        "applies_to_fields": ["control_unavailable_reasons", "fallback_level"],
        "spec": {
            "module_function": UNAVAILABLE_EXECUTOR,
            "version": "1",
            "contract_note": (
                "returns HTTP 200 with outcome='control_unavailable', the reasons verbatim and"
                " every figure slot present and null; it never omits the figure and never"
                " answers 404 for a subject the control covers"
            ),
            "reasons": ["insufficient_peers", "missing_lateral_length"],
            "served_as": "stated_outcome_with_null_valued_figure_slots",
        },
        "code_ref": UNAVAILABLE_EXECUTOR,
        "rule": (
            "A subject whose control did not resolve is served as a stated outcome naming its"
            " reasons, never as an absent figure."
        ),
        "rationale": (
            "The control terminates at control_unavailable for 1.08 per cent of subject"
            " instances, and the reasons are already recorded on the row. Dropping those rows"
            " from the response would let a caller read the served population as the whole"
            " test population and compute a coverage number that is silently wrong by that"
            " margin. Serving the outcome instead keeps the absence addressable and keeps its"
            " handle resolvable to the rung that terminated. A serving decision this release"
            " makes; recorded as code_ref because the executor is the router the spec names."
        ),
        "evidence_url": MPR_INDEX_URL,
        "effective_from": SERVING_FROM,
    },
)

_INSERT = """
insert into lineage.conformance_rules
    (rule_id, rule_family, supersedes_rule_id, source_id, stage, applies_to_fields, rule_kind,
     spec, rule, rationale, evidence_url, code_ref, effective_from)
values (%(rule_id)s, %(rule_family)s, %(supersedes_rule_id)s, %(source_id)s, %(stage)s,
        %(applies_to_fields)s, %(rule_kind)s, %(spec)s, %(rule)s, %(rationale)s,
        %(evidence_url)s, %(code_ref)s, %(effective_from)s)
on conflict do nothing
"""


def _row(rule: dict[str, object]) -> dict[str, object]:
    rule_id = str(rule["rule_id"])
    return {
        **rule,
        "rule_family": rule_id.rsplit("_", 1)[0],
        "spec": Jsonb(rule["spec"]),
        "code_ref": rule.get("code_ref"),
        "supersedes_rule_id": rule.get("supersedes_rule_id"),
        "effective_from": rule.get("effective_from", SERVING_FROM),
    }


def seed_conformance_typecurve(connection: psycopg.Connection) -> int:
    """Counted by explicit rule id, not by source: these rows share nd_mpr_xlsx with the ND
    registry, whose own count is a total over that prefix."""
    with connection.cursor() as cursor:
        cursor.executemany(_INSERT, [_row(rule) for rule in TYPECURVE_RULES])
        cursor.execute(
            "select count(*) from lineage.conformance_rules where rule_id = any(%s)",
            ([str(rule["rule_id"]) for rule in TYPECURVE_RULES],),
        )
        return int(cursor.fetchone()[0])
