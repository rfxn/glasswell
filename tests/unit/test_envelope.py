from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any
from urllib.parse import parse_qsl, quote, urlsplit

import pytest

from glasswell.lineage.envelope import (
    ENVELOPE_META_KEYS,
    InlinedExplain,
    attach_lineage,
    figure,
    series,
)
from glasswell.lineage.errors import InvalidHandle, InvalidSelector

DERIVATION = "drv_7qk3m2xr4v9b"
SELECTOR = "api10=3305301234&col=cum12_oil"
AS_OF = date(2026, 8, 1)


def oil_figure(**overrides: Any):
    arguments: dict[str, Any] = {
        "unit": "bbl",
        "derivation": DERIVATION,
        "selector": SELECTOR,
        "granularity": "well_observed",
        "basis": "oil+condensate",
        "report_vintage": date(2026, 8, 1),
    }
    arguments.update(overrides)
    return figure(Decimal("128340.000"), **arguments)


def envelope_of(data: Any):
    return attach_lineage(data, as_of=AS_OF, request_id="req_01").to_dict()


def test_inline_invalid_selector_is_an_explicit_non_destructive_warning():
    value = oil_figure()
    body = attach_lineage(
        {"oil": value},
        as_of=AS_OF,
        request_id="req_selector_warning",
        explain=lambda handles: InlinedExplain(
            chains={}, unresolved=dict.fromkeys(handles, "invalid_selector")
        ),
    ).to_dict()

    warning = next(
        item for item in body["meta"]["warnings"] if item["code"] == "explain_invalid_selector"
    )
    assert value.handle in warning["detail"]
    assert body["data"]["oil"]["value"] == "128340.000"
    assert body["_explain"] == {}


def test_a_figure_without_a_unit_is_rejected_at_construction():
    with pytest.raises(ValueError, match="unit"):
        oil_figure(unit="")


def test_a_production_figure_without_granularity_is_rejected():
    with pytest.raises(ValueError, match="granularity"):
        oil_figure(granularity=None)


def test_a_liquids_figure_without_a_basis_is_rejected():
    with pytest.raises(ValueError, match="basis"):
        oil_figure(basis=None)


def test_a_gas_figure_needs_no_basis():
    gas = figure(
        Decimal("41120.000"),
        unit="mcf",
        derivation=DERIVATION,
        granularity="well_observed",
        report_vintage=date(2026, 8, 1),
    )
    assert gas.to_wire()["unit"] == "mcf"
    assert "basis" not in gas.to_wire()


def test_an_allocated_figure_must_name_its_allocation_model():
    with pytest.raises(ValueError, match="allocation_model_id"):
        oil_figure(granularity="lease_allocated")


def test_an_undeclared_granularity_is_rejected():
    with pytest.raises(ValueError, match="granularity"):
        oil_figure(granularity="estimated")


def test_the_handle_is_validated_at_construction():
    with pytest.raises(InvalidSelector):
        oil_figure(selector="api10 = 3305301234; drop table")


def test_the_envelope_has_exactly_the_sb04_2_2_shape():
    envelope = envelope_of({"cum12_oil": oil_figure()})
    assert set(envelope) == {"data", "meta", "links"}
    assert set(envelope["meta"]) == set(ENVELOPE_META_KEYS)
    assert set(envelope["links"]) == {"self", "next", "explain"}
    assert envelope["meta"]["as_of"] == {"requested": "latest", "resolved": "2026-08-01"}


def test_the_envelope_carries_no_parallel_lineage_map():
    # SB-04 errata E-01: the in-band figure object is the only representation of a handle.
    envelope = envelope_of({"cum12_oil": oil_figure()})
    assert "derivations" not in envelope["meta"]
    assert "units" not in envelope["meta"]


def test_a_figure_serializes_to_the_sb07_9_1_a_form():
    envelope = envelope_of({"cum12_oil": oil_figure()})
    assert envelope["data"]["cum12_oil"] == {
        "value": "128340.000",
        "unit": "bbl",
        "basis": "oil+condensate",
        "granularity": "well_observed",
        "report_vintage": "2026-08-01",
        "d": f"{DERIVATION}#{SELECTOR}",
    }


def test_an_allocated_figure_states_the_model_that_produced_it():
    allocated = oil_figure(granularity="lease_allocated", allocation_model_id="alloc_v0_2026_07")
    assert allocated.to_wire()["allocation_model_id"] == "alloc_v0_2026_07"
    assert allocated.to_wire()["granularity"] == "lease_allocated"


def test_a_series_selector_is_validated_like_a_figure_selector():
    with pytest.raises(InvalidSelector):
        series([1], unit="mcf", derivation=DERIVATION, selector="api10 = 3305301234")


def test_a_dense_series_carries_one_handle_in_a_sidecar():
    envelope = envelope_of(
        {
            "series": {
                "pm": ["2024-01", "2024-02"],
                "oil_bbl": series(
                    [Decimal("12034.000"), Decimal("11120.000")],
                    unit="bbl",
                    derivation=DERIVATION,
                    basis="oil+condensate",
                ),
            }
        }
    )
    assert envelope["data"]["series"]["oil_bbl"] == ["12034.000", "11120.000"]
    assert envelope["data"]["_lineage"] == {"series.oil_bbl": DERIVATION}
    assert envelope["data"]["_units"] == {"series.oil_bbl": "bbl"}
    assert envelope["data"]["_basis"] == {"series.oil_bbl": "oil+condensate"}


def test_points_that_disagree_carry_a_handle_each():
    """D3: one handle per point when the points come from different promotions."""
    envelope = envelope_of(
        {
            "series": {
                "pm": ["2025-12", "2026-01"],
                "oil_bbl": series(
                    [Decimal("31535.000"), Decimal("15478.000")],
                    unit="bbl",
                    derivation=DERIVATION,
                    basis="oil+condensate",
                    point_handles=[f"{DERIVATION}#pm=2025-12", "drv_other01#pm=2026-01"],
                ),
            }
        }
    )
    assert envelope["data"]["_lineage"] == {
        "series.oil_bbl.0": f"{DERIVATION}#pm=2025-12",
        "series.oil_bbl.1": "drv_other01#pm=2026-01",
    }
    assert envelope["data"]["_units"] == {"series.oil_bbl": "bbl"}
    # Percent-encoded, per MINOR-5: a `#` sent raw makes the rest of the link a fragment the
    # server never sees, so every point handle would resolve to a bare derivation.
    assert envelope["links"]["explain"] == (
        f"/v1/explain?h={DERIVATION}%23pm%3D2025-12&h=drv_other01%23pm%3D2026-01&depth=full"
    )


def test_a_point_without_a_value_carries_no_handle():
    envelope = envelope_of(
        {
            "series": {
                "oil_bbl": series(
                    [Decimal("1"), None],
                    unit="mcf",
                    derivation=DERIVATION,
                    point_handles=[f"{DERIVATION}#pm=2025-12", None],
                )
            }
        }
    )
    assert set(envelope["data"]["_lineage"]) == {"series.oil_bbl.0"}


def test_point_handles_must_align_with_the_values():
    with pytest.raises(ValueError, match="one-to-one"):
        series([1, 2], unit="mcf", derivation=DERIVATION, point_handles=[DERIVATION])


def test_a_point_handle_is_validated_like_any_other_handle():
    with pytest.raises(InvalidHandle):
        series([1], unit="mcf", derivation=DERIVATION, point_handles=["not-a-handle"])


def test_a_collection_hangs_its_sidecars_on_each_item():
    envelope = envelope_of(
        [
            {"api10": "3305301234", "oil": series([1, 2], unit="mcf", derivation=DERIVATION)},
            {"api10": "3305305678", "oil": series([3], unit="mcf", derivation="drv_other01")},
        ]
    )
    assert envelope["data"][0]["_lineage"] == {"oil": DERIVATION}
    assert envelope["data"][1]["_lineage"] == {"oil": "drv_other01"}
    assert "_basis" not in envelope["data"][0]


def test_an_object_without_a_series_gets_no_sidecar_keys():
    envelope = envelope_of({"cum12_oil": oil_figure()})
    assert set(envelope["data"]) == {"cum12_oil"}


def test_the_explain_link_is_prebuilt_from_the_handles_in_the_response():
    envelope = envelope_of({"well": {"cum12_oil": oil_figure()}, "rows": [oil_figure()]})
    handle = quote(f"{DERIVATION}#{SELECTOR}", safe="")

    assert envelope["links"]["explain"] == f"/v1/explain?h={handle}&depth=full"
    # The `#` a cell handle carries must not survive into the link as a fragment separator.
    assert "#" not in envelope["links"]["explain"]


def test_a_hand_authored_explain_link_is_refused_not_honoured():
    """gate-apix ADV-1: a router-authored link and `inline_handles()` are two carriers of
    "which handles will you resolve", demonstrated to disagree. The envelope is the only
    author now, so the divergence is unconstructible rather than merely untriggered."""
    with pytest.raises(ValueError, match="envelope-authored"):
        attach_lineage(
            {"cum12_oil": oil_figure()},
            as_of=AS_OF,
            request_id="req_02",
            links={"self": "/v1/wells/3305301234", "explain": "/v1/explain?h=drv_other01"},
        )


def test_a_fragment_smuggled_handle_is_refused_like_a_query_one():
    """gate-apiconv §9.3: `#h=x` is not query, so it slipped the refusal on a handle-less
    response. A link that names a handle in any position is a second author and is refused."""
    with pytest.raises(ValueError, match="envelope-authored"):
        attach_lineage(
            {"api_version": "v1"},
            as_of=AS_OF,
            request_id="req_02",
            links={"self": "/v1", "explain": "/v1/explain#h=drv_other01"},
        )


def test_the_shapes_that_pass_the_guard_are_exactly_the_ones_no_parser_reads():
    """RN-1 closed. `%23h=`, `#h%3D` and `##h=` pass `_names_handles` — and must: `parse_qsl`
    reads no `h` key in any of them, so a resolver handed the same link finds no handle set
    either. Parser-symmetric means no divergence channel. The guard's input is
    router-authored (never client-supplied) and fragments never cross HTTP, so the only
    server-reachable reading of each shape is its one-step-decoded neighbour — refused."""
    shapes = (
        ("/v1/explain?%23h=drv_other01", "/v1/explain?#h=drv_other01"),
        ("/v1/explain#h%3Ddrv_other01", "/v1/explain#h=drv_other01"),
        ("/v1/explain##h=drv_other01", "/v1/explain#h=drv_other01"),
    )
    for smuggled, decoded in shapes:
        parts = urlsplit(smuggled)
        pairs = parse_qsl(parts.query, keep_blank_values=True) + parse_qsl(
            parts.fragment, keep_blank_values=True
        )
        assert not [value for key, value in pairs if key == "h"], smuggled

        passed = attach_lineage(
            {"api_version": "v1"},
            as_of=AS_OF,
            request_id="req_02",
            links={"self": "/v1", "explain": smuggled},
        ).to_dict()
        assert passed["links"]["explain"] == smuggled

        with pytest.raises(ValueError, match="envelope-authored"):
            attach_lineage(
                {"api_version": "v1"},
                as_of=AS_OF,
                request_id="req_02",
                links={"self": "/v1", "explain": decoded},
            )


def test_a_handle_less_template_passes_and_is_overwritten_the_moment_handles_exist():
    """The service index links `/v1/explain?h=` as a navigation template. Naming no handle,
    it can disagree with nothing — but on a response that does carry handles, the envelope's
    own link is the only carrier and the template loses."""
    template = {"self": "/v1", "explain": "/v1/explain?h="}
    index_like = attach_lineage(
        {"api_version": "v1"}, as_of=AS_OF, request_id="req_02", links=template
    ).to_dict()
    handle_bearing = attach_lineage(
        {"cum12_oil": oil_figure()}, as_of=AS_OF, request_id="req_02", links=template
    ).to_dict()
    handle = quote(f"{DERIVATION}#{SELECTOR}", safe="")

    assert index_like["links"]["explain"] == "/v1/explain?h="
    assert handle_bearing["links"]["explain"] == f"/v1/explain?h={handle}&depth=full"


def test_a_link_mapping_with_a_null_explain_is_not_a_hand_authored_link():
    envelope = attach_lineage(
        {"cum12_oil": oil_figure()},
        as_of=AS_OF,
        request_id="req_02",
        links={"self": "/v1/wells/3305301234", "explain": None},
    ).to_dict()
    handle = quote(f"{DERIVATION}#{SELECTOR}", safe="")
    assert envelope["links"]["explain"] == f"/v1/explain?h={handle}&depth=full"
    assert envelope["links"]["self"] == "/v1/wells/3305301234"
    assert envelope["links"]["next"] is None


def test_extra_handles_reach_the_link_through_the_same_selection():
    """A record whose subject is a derivation spells no figure, so the walk finds nothing;
    `extra_handles` feeds the one selection both carriers read instead of a second link."""
    envelope = attach_lineage(
        {"derivation_id": "drv_subject01"},
        as_of=AS_OF,
        request_id="req_02",
        extra_handles=["drv_subject01"],
    ).to_dict()
    assert envelope["links"]["explain"] == "/v1/explain?h=drv_subject01&depth=full"


def test_a_router_written_sidecar_feeds_the_link_the_walk_builds():
    """`/v1/vintages` writes §9.1(b) sidecars by hand; their handles are the response's, so
    the envelope collects them — the router builds no link of its own."""
    envelope = attach_lineage(
        [
            {"rows_appended": 19, "_lineage": {"rows_appended": "drv_promotion1"}},
            {"rows_appended": 3, "_lineage": {"rows_appended": "drv_promotion2"}},
            {"rows_appended": 7},
        ],
        as_of=AS_OF,
        request_id="req_02",
    ).to_dict()
    assert (
        envelope["links"]["explain"] == "/v1/explain?h=drv_promotion1&h=drv_promotion2&depth=full"
    )
    assert envelope["data"][0]["_lineage"] == {"rows_appended": "drv_promotion1"}


def test_meta_carries_labels_warnings_deprecations_and_freshness():
    envelope = attach_lineage(
        {"cum12_oil": oil_figure()},
        as_of=AS_OF,
        request_id="req_03",
        as_of_requested="2026-07-01",
        warnings=["one source is stale", {"code": "explain_truncated", "detail": "depth 8"}],
        labels={"/cum12_oil": "gls_cum12"},
        source_freshness={"nd_mpr_xlsx": {"state": "current"}},
        next_cursor="cur_02",
        deprecations=[{"code": "field_renamed", "detail": "oil_bbl"}],
    ).to_dict()
    assert envelope["meta"]["request_id"] == "req_03"
    assert envelope["meta"]["as_of"]["requested"] == "2026-07-01"
    assert envelope["meta"]["labels"] == {"/cum12_oil": "gls_cum12"}
    assert envelope["meta"]["warnings"] == [
        {"code": "warning", "detail": "one source is stale"},
        {"code": "explain_truncated", "detail": "depth 8"},
    ]
    assert envelope["meta"]["deprecations"] == [{"code": "field_renamed", "detail": "oil_bbl"}]
    assert envelope["meta"]["source_freshness"] == {"nd_mpr_xlsx": {"state": "current"}}
    assert envelope["meta"]["next_cursor"] == "cur_02"
