"""A3-F1: the length method is a rule row, and only this module turns it into SQL."""

from __future__ import annotations

from datetime import date

import pytest

from glasswell.lengths import compute_crs_rule, length_method
from glasswell.lineage.errors import RuleSpecError
from glasswell.lineage.models import ConformanceRule


def crs_rule(rule_id: str, spec: dict) -> ConformanceRule:
    return ConformanceRule(
        rule_id=rule_id,
        rule_family=rule_id.rsplit("_", 1)[0],
        source_id="nd_gis_horizontals_line",
        stage="conform",
        applies_to_fields=["geom"],
        rule_kind="parse_directive",
        spec=spec,
        rule="test rule",
        rationale="test rationale",
        effective_from=date(2026, 8, 20),
    )


GEODESIC_RULE = crs_rule("cr_nd_compute_crs_2", {"length_method": "geodesic"})
PROJECTED_RULE = crs_rule(
    "cr_nd_compute_crs_1", {"length_method": "projected", "compute_epsg": 32614}
)


def test_the_geodesic_method_measures_on_the_ellipsoid_and_names_no_zone():
    method = length_method(GEODESIC_RULE)

    assert method.metres_sql("s.geom") == "ST_Length(s.geom::geography)"
    assert method.compute_crs == "EPSG:4326"
    assert method.compute_epsg is None


def test_the_projected_method_keeps_the_transform_it_declares():
    method = length_method(PROJECTED_RULE)

    assert method.metres_sql() == "ST_Length(ST_Transform(geom, 32614))"
    assert method.compute_crs == "EPSG:32614"


def test_a_projected_rule_without_an_epsg_is_refused():
    with pytest.raises(RuleSpecError, match="compute_epsg"):
        length_method(crs_rule("cr_nd_compute_crs_9", {"length_method": "projected"}))


def test_an_undeclared_method_is_refused_rather_than_interpolated():
    """The spec is registry data; only allowlisted tokens ever reach a statement."""
    with pytest.raises(RuleSpecError, match="length_method"):
        length_method(
            crs_rule(
                "cr_nd_compute_crs_9",
                {"length_method": "ST_Length(geom) -- ; drop table canonical.wells"},
            )
        )


def test_the_family_is_what_selects_the_rule_not_a_pinned_id():
    """A supersession changes the id; a consumer that pins the id would miss the new rule."""
    assert compute_crs_rule([GEODESIC_RULE]).rule_id == "cr_nd_compute_crs_2"

    with pytest.raises(LookupError, match="cr_nd_compute_crs"):
        compute_crs_rule([])
