"""The martin catalogue against the proxy's allowlist, in the tier a tiered run collects.

Both assertions below need no fixture and no container, and both lived under
`tests/integration/`. `tests/conftest.py` marks by directory, so `pytest -m unit` -- and any
tiered CI run -- deselected the only infrastructure-free martin gate in the tree. The layer
declarations and the config file are all either of them reads, so the honest tier is this one.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from glasswell.api.routers.tiles import PUBLISHED_LAYERS
from glasswell.marts.tiles import TILE_LAYERS

pytestmark = pytest.mark.unit

MARTIN_CONFIG = Path(__file__).resolve().parents[2] / "infra" / "martin" / "config.yaml"


def config() -> dict:
    return yaml.safe_load(MARTIN_CONFIG.read_text(encoding="utf-8"))


def test_the_martin_config_publishes_the_functions_the_allowlist_names() -> None:
    """The config is what martin publishes; TILE_LAYERS is what the proxy admits (DR-05).

    The sources are the tile functions, so the property list martin serves *is* the function's
    own select list — there is no second declaration of types to drift out of step with the
    relation, which is the N-2 class removed rather than re-guarded."""
    postgres = config()["postgres"]
    assert postgres["auto_publish"] is False
    assert set(postgres["functions"]) == {layer.name for layer in TILE_LAYERS}
    for layer in TILE_LAYERS:
        declared = postgres["functions"][layer.name]
        assert declared["schema"] == "marts"
        assert declared["function"] == layer.name


def test_the_martin_config_declares_the_same_layers_the_proxy_admits() -> None:
    """The config is what the adopted unit publishes; the proxy's allowlist is what it will
    answer for. The two must not drift apart."""
    document = config()
    postgres = document["postgres"]

    assert document["listen_addresses"] == "127.0.0.1:3000"
    assert set(postgres["functions"]) == PUBLISHED_LAYERS == {layer.name for layer in TILE_LAYERS}
    for layer in TILE_LAYERS:
        source = postgres["functions"][layer.name]
        assert source["schema"] == "marts"
        assert source["function"] == layer.name
        assert "derivation_id" in layer.columns, f"{layer.name} serves an unhandled figure"
    # Publishing the same ids twice — once as functions, once as the tables they read — is a
    # martin id collision, so the config carries exactly one mechanism.
    assert "tables" not in postgres


def test_this_file_collects_under_the_unit_tier() -> None:
    """The whole point of the move: a directory-marked contract, asserted rather than assumed."""
    assert "/tests/unit/" in Path(__file__).resolve().as_posix()
    assert pytestmark.name == "unit"
