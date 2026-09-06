"""The status-history rules: which clock a header's effective_from is, per jurisdiction.

The rule is what makes an empty status history readable. Without it a consumer cannot tell
"this well never changed" from "no history was ever captured here", and the two are different
facts about different things -- the well, and the pipeline.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

import glasswell
from glasswell.api.routers import wells
from glasswell.seed.conformance_status_history import (
    CLOCKS,
    CO_HISTORY_RULE_ID,
    HISTORY_RULE_IDS,
    HISTORY_RULES,
    LOAD_STAMP,
    NM_HISTORY_RULE_ID,
    REGISTERS,
    SOURCE_VALID_TIME,
    STATUS_HISTORY,
)
from glasswell.seed.jurisdictions import JURISDICTION_RULES, JURISDICTIONS

pytestmark = pytest.mark.unit

REGISTERS_TO_RULE = {"NM": NM_HISTORY_RULE_ID, "CO": CO_HISTORY_RULE_ID}

BY_ID = {str(rule["rule_id"]): rule for rule in HISTORY_RULES}
RULE = BY_ID[NM_HISTORY_RULE_ID]
SPEC = RULE["spec"]
ROUTER_SOURCE = (Path(glasswell.__file__).parent / "api" / "routers" / "wells.py").read_text()


def test_it_is_one_row_per_registering_jurisdiction_under_that_jurisdiction_s_own_source() -> (
    None
):
    """One shared row served New Mexico's OCD archive as the evidence for a decision about
    Colorado's clock, which is the failure R8 exists to prevent (gate H-1)."""
    assert set(BY_ID) == set(HISTORY_RULE_IDS) == set(REGISTERS_TO_RULE.values())
    assert BY_ID[NM_HISTORY_RULE_ID]["source_id"] == "nm_ocd_wellhistory"
    assert BY_ID[CO_HISTORY_RULE_ID]["source_id"] == "co_ecmc_wells_shp"
    assert "emnrd.nm.gov" in str(BY_ID[NM_HISTORY_RULE_ID]["evidence_url"])
    assert "ecmc.state.co.us" in str(BY_ID[CO_HISTORY_RULE_ID]["evidence_url"])
    for rule in HISTORY_RULES:
        # P3.0's convention, which one global id broke: the id names the table its source holds.
        assert str(rule["rule_id"]).startswith("cr_nm_") or str(rule["rule_id"]).startswith(
            "cr_co_"
        )
        assert rule["code_ref"] == "glasswell.api.routers.wells:get_well_status_history"
        assert rule["rationale"]


def test_the_registry_points_each_jurisdiction_at_its_own_rule() -> None:
    declared = {
        str(row["jurisdiction_code"]): str(row["rule_id"])
        for row in JURISDICTION_RULES
        if row["decision"] == STATUS_HISTORY
    }
    assert declared == REGISTERS_TO_RULE


def test_every_registered_jurisdiction_carries_a_clock_and_its_own_effective_rule() -> None:
    """A jurisdiction the rule does not mention is one whose absence nobody decided."""
    registered = {str(row["jurisdiction_code"]) for row in JURISDICTIONS}
    assert registered <= set(CLOCKS), sorted(registered - set(CLOCKS))
    for code, clock in CLOCKS.items():
        assert clock["clock"] in {SOURCE_VALID_TIME, LOAD_STAMP}, code
        assert clock["effective_rule"], code
        assert clock["effective_from_is"], code


def test_it_registers_for_the_valid_time_jurisdictions_and_for_nobody_else() -> None:
    # The registration is the whole decision: the router asks the registry whether this
    # jurisdiction carries the status_history decision and emits links.history from that alone.
    assert set(REGISTERS) == {
        code for code, clock in CLOCKS.items() if clock["clock"] == SOURCE_VALID_TIME
    }
    assert set(REGISTERS) == {"NM", "CO"}
    assert SPEC["registers_for"] == list(REGISTERS)
    assert SPEC["decision"] == STATUS_HISTORY
    assert SPEC["emits"] == "links.history"


def test_the_measurement_behind_it_is_in_the_row_rather_than_in_a_commit_message() -> None:
    measured = SPEC["measured"]
    # Measured on the deployed spine 2026-09-03. Zero canonical changes is why the axis is the
    # filed code; 31,707 changed filed codes is why there is anything to serve at all.
    assert measured["wells_whose_status_canonical_ever_changes"] == 0
    assert measured["wells_whose_status_reported_ever_changes"] == 31707
    assert measured["distinct_effective_dates"] == {"NM": 15590, "ND": 2, "MT": 1, "TX": 1}
    assert CLOCKS["NM"]["distinct_effective_dates"] == 15590
    assert CLOCKS["NM"]["wells_with_a_changed_filed_code"] == 31707
    for number in ("31,707", "15,590", "585,864"):
        assert number in str(RULE["rationale"])


def test_the_axis_is_the_filed_code_and_the_class_column_says_what_it_is() -> None:
    assert SPEC["axis"] == "status_reported"
    assert SPEC["not_the_axis"] == "status_canonical"
    assert SPEC["class_column_label"] == "class as glasswell maps this code today"
    assert SPEC["class_column_is_historical"] is False
    assert SPEC["class_column_resolver"] == "glasswell.status_resolution:resolver_join"
    assert SPEC["class_column_label"] == wells.CLASS_COLUMN_LABEL


def test_the_router_maps_a_status_nowhere_of_its_own() -> None:
    """status_resolution.py:1-12 exists so one resolver answers for every surface. A second
    mapping in the router is exactly the drift it was written to prevent."""
    produced = re.findall(r"([\w{}().'\"]+)\s+as status_canonical", ROUTER_SOURCE)
    assert produced, "the scan found no status_canonical projection to check"
    assert all("resolved" in each.lower() for each in produced), produced
    for mapping_table in ("nm_wellhistory_status_map", "co_facility_status_map", "status_map"):
        assert mapping_table not in ROUTER_SOURCE, mapping_table


def test_the_history_reads_the_base_tables_and_needs_no_ddl() -> None:
    """A view is DDL and migrate.py is the only path that applies it. This operation is an
    indexed scalar join onto a table that already exists, which is why v0.80 spends one
    migration and not two."""
    assert "from canonical.wells w" in wells.STATUS_HISTORY_SQL
    assert "canonical.status_resolution" in wells.STATUS_HISTORY_SQL
    assert "order by w.effective_from desc" in wells.STATUS_HISTORY_SQL
    assert wells.STATUS_HISTORY_CAP == SPEC["cap"] == 10
    migrations = sorted((Path(glasswell.__file__).parent / "db" / "migrations").glob("*.sql"))
    # The rule id appears in exactly one migration and only to publish it: publication evidence
    # is what brings a rule id into existence at all (049's trigger refuses the insert without
    # it), and it is DML in an append-only table rather than DDL.
    for rule_id in HISTORY_RULE_IDS:
        naming = [path for path in migrations if rule_id in path.read_text()]
        assert len(naming) == 1, [path.name for path in naming]
        assert "conformance_rule_publications" in naming[0].read_text()
    # Nothing anywhere creates a relation for this operation to read: it joins the base tables
    # a jurisdiction's headers already live in, which is why v0.80 spends one migration.
    ddl = re.compile(
        r"create\s+(or\s+replace\s+)?(view|materialized\s+view|table)\s+"
        r"(if\s+not\s+exists\s+)?[\w.]*status_history",
        re.IGNORECASE,
    )
    assert not any(ddl.search(path.read_text()) for path in migrations)
