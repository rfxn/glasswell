"""The profile rows, held to what the four mart modules emitted at v0.76, with no database.

`lineage/ids.py` hashes `hash_payload(params)` and `ruleset_hash(rule_ids)` into every
derivation id, and `hash_payload` sorts keys over the whole dict -- so adding or removing one
params key moves the address. The four modules had three distinct params key sets and four
distinct rule lists, and this file is what refuses a profile that tidied either of them up.

`scripts/mart-address-diff.sh` proves the same property end to end and needs docker; this fails
first, and says which of the two it was.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from glasswell.marts import wells
from glasswell.marts.wells import (
    LENGTH_SCOPE,
    LENGTH_SOURCE,
    MART_PROFILES,
    MartProfileError,
    length_binding_error,
    profile_for,
)
from glasswell.seed.jurisdictions import JURISDICTION_RULES, rule_parameters

pytestmark = pytest.mark.unit

# Verbatim from v0.76's `rules=[...]`, minus the compute-CRS rule the engine still prepends
# where a length is served. Four lists, deliberately not one: `ruleset_hash` is
# `hash_payload(sorted(set(rule_ids)))`, so de-duplication cannot absorb an addition and
# unioning the registry's own rows into these would have moved all four hashes.
FROZEN_RULE_IDS = {
    "ND": ("cr_nd_datum_1", "cr_nd_geometry_provenance_1"),
    "TX": ("cr_tx_nad27_1",),
    "NM": (
        "cr_nm_wellhistory_datum_1",
        "cr_nm_wellhistory_geometry_provenance_1",
        "cr_nm_wellhistory_geometry_scope_1",
        "cr_nm_wellhistory_status_vocab_2",
    ),
    "MT": (
        "cr_mt_basin_scope_1",
        "cr_mt_gis_datum_1",
        "cr_mt_paths_datum_1",
        "cr_mt_paths_geometry_class_1",
        "cr_mt_paths_coverage_1",
        "cr_mt_paths_subkey_1",
        "cr_mt_gis_status_vocab_1",
    ),
}

# The params key sets as v0.76 emitted them: ND and TX five keys, MT six, NM four. The engine
# adds `length_method` and `compute_epsg` only where a length is served, which is what keeps
# North Dakota's set at five and New Mexico's at four rather than giving everyone six.
FROZEN_PARAMS_KEYS = {
    "ND": {"as_of", "length_method", "compute_epsg", "state_code", "layers"},
    "TX": {"as_of", "length_method", "compute_epsg", "state_code", "layers"},
    "NM": {"as_of", "state_code", "geometry_scope", "layers"},
    "MT": {"as_of", "state_code", "basin", "geometry_class", "length_served", "layers"},
}

FROZEN_DATASETS = {
    "ND": "marts.nd_tiles",
    "TX": "marts.tx_tiles",
    "NM": "marts.nm_tiles",
    "MT": "marts.mt_tiles",
}

LENGTH_SERVING = {"ND", "TX"}


def profile_params_keys(code: str) -> set[str]:
    profile = profile_for(code)
    keys = {"as_of", "state_code", "layers", *(key for key, _ in profile.params_extra)}
    if code in LENGTH_SERVING:
        keys |= {"length_method", "compute_epsg"}
    return keys


@pytest.mark.parametrize("code", sorted(FROZEN_RULE_IDS))
def test_each_profile_cites_exactly_the_rules_its_module_cited(code: str) -> None:
    assert profile_for(code).rule_ids == FROZEN_RULE_IDS[code]


@pytest.mark.parametrize("code", sorted(FROZEN_PARAMS_KEYS))
def test_no_params_key_set_moved(code: str) -> None:
    assert profile_params_keys(code) == FROZEN_PARAMS_KEYS[code]


@pytest.mark.parametrize("code", sorted(FROZEN_DATASETS))
def test_each_profile_publishes_the_dataset_and_partition_its_module_published(
    code: str,
) -> None:
    assert profile_for(code).dataset == FROZEN_DATASETS[code]
    assert profile_for(code).jurisdiction_code == code


def test_montana_keeps_the_null_basin_key_texas_does_not_carry() -> None:
    """An asymmetry, preserved verbatim, because the address depends on it: Montana names a
    basin it does not have and Texas, which has one, names none."""
    assert dict(profile_for("MT").params_extra)["basin"] is None
    assert "basin" not in dict(profile_for("TX").params_extra)


def test_north_dakota_alone_publishes_four_layers_against_three_projections() -> None:
    profile = profile_for("ND")

    assert len(profile.layers) == 4
    assert len(profile.projections) == 3


@pytest.mark.parametrize("code", sorted(FROZEN_RULE_IDS))
def test_a_length_column_is_bound_to_a_registration_that_serves_one(code: str) -> None:
    """N-23, both directions. A registration that starts withholding would otherwise leave
    `{length_metres}` unfilled, which is a KeyError inside a refresh rather than a refusal."""
    profile = profile_for(code)
    declared = {
        (str(row["jurisdiction_code"]), str(row["decision"])): str(row["rule_id"])
        for row in (rule_parameters(rule) for rule in JURISDICTION_RULES)
        if row["serving"]
    }
    withheld = declared.get((code, LENGTH_SCOPE))

    assert (code in LENGTH_SERVING) == profile.serves_a_length
    assert length_binding_error(profile, withheld) is None
    if profile.serves_a_length:
        assert declared.get((code, LENGTH_SOURCE)) is not None
    else:
        assert declared.get((code, LENGTH_SOURCE)) is None


def test_a_withholding_registration_over_a_length_profile_is_refused_not_discovered() -> None:
    problem = length_binding_error(profile_for("ND"), "cr_nd_planted_length_scope_1")

    assert problem is not None
    assert "cr_nd_planted_length_scope_1" in problem
    assert "publishes a length column" in problem


def test_an_unregistered_jurisdiction_has_no_profile_and_says_so() -> None:
    """Wyoming rather than Colorado: Colorado is a registered profile now, and a refusal test
    keyed on a code the engine answers for proves the opposite of what it is written for."""
    with pytest.raises(MartProfileError) as refused:
        profile_for("WY")

    assert "WY" in str(refused.value)
    assert "ND" in str(refused.value)
    assert "CO" in str(refused.value), "the refusal has to list the profiles that do exist"


def test_the_constant_the_length_default_lived_in_has_no_caller_left_in_the_marts() -> None:
    """M-18. `lengths.LATERALS_SOURCE_ID` was the module constant a mart passed straight in;
    the source is a registration now, so a repoint moves `method.rule_id` with the number."""
    from pathlib import Path

    import glasswell.marts as marts

    package = Path(marts.__file__).parent
    for module in sorted(package.glob("*.py")):
        assert "LATERALS_SOURCE_ID" not in module.read_text(encoding="utf-8"), module.name


def test_every_profile_names_a_registered_jurisdiction() -> None:
    from glasswell.seed.jurisdictions import CODES

    assert {profile.jurisdiction_code for profile in MART_PROFILES} <= CODES


def test_a_fifth_state_is_a_profile_row_and_not_a_module() -> None:
    """The claim the Colorado track exists to make: a fifth state adds a row to the engine."""
    assert not (Path(wells.__file__).parent / "co_wells.py").exists()
    profile = wells.profile_for("CO")
    assert profile.dataset == "marts.co_tiles"
    assert [layer.name for layer in profile.layers] == ["co_wells"]
