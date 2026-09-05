"""Read-time application of blank-is-absent, for rows promoted before the rule existed.

`cr_co_wells_shp_blank_is_absent_1` and its two sibling layers say a blank ECMC attribute is an
absence, and `ingest/co_ecmc_gis.py` stages under it. The 124,392 Colorado headers promoted
before it existed cannot be corrected the same way: `canonical.wells` is keyed
(api10, effective_from), Colorado's `effective_from` is ECMC's own Stat_Date under
`cr_co_wells_effective_1`, so a restatement carries the key of the row it restates and the
append is refused -- and an effective date the regulator never filed is the invention
`ingest/co_wells.py` already refuses for `status_canonical`. An edit is refused outright: R8
appends restatements and never applies them.

So the rule is applied where those rows are read. It lives here rather than at any one call
site for the reason `status_resolution.py` gives about the class: the tile mart, the well card
and the status summary must not answer differently about the same well on the same screen. The
model context (`lineage/as_of.py`) reads `area` under it too -- an unserved read, but a blank
there is a control-feature category of its own rather than the absence it is.
"""

from __future__ import annotations

# What the promotion writes from a source-reported text column, and therefore what a read has
# to apply the rule to.
SOURCE_REPORTED_TEXT_COLUMNS: tuple[str, ...] = (
    "county_code_at_permit",
    "ndic_file_no",
    "operator_name_reported",
    "operator_id",
    "well_name",
    "status_reported",
    "well_type_reported",
)

# The rest of canonical.wells' text columns. api10, api14 and state_code are built under the
# identity rules, basin and land_unit_label are glasswell's own assignments, status_canonical is
# its class and the two ids are lineage's -- no source files any of them, blank or otherwise.
# Named rather than described so both sets can be held to the table: a seventh source-reported
# column cannot land on the spine without joining one of them.
NOT_SOURCE_REPORTED: tuple[str, ...] = (
    "api10",
    "api14",
    "state_code",
    "basin",
    "land_unit_label",
    "status_canonical",
    "source_manifest_id",
    "derivation_id",
)


def absent_if_blank(column: str) -> str:
    """`column` with the empty string read as the absence it is."""
    return f"nullif({column}, '')"
