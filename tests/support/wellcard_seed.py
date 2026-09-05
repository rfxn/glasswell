"""Track-local shot fixture for the well card. Exec'd through `GW_SEED` with `connection` bound.

Two shapes `serve_branch.py` does not seed and the card's postures cannot be photographed
without: a surface point, so the rail's Locate control is present under its own rule, and a
Colorado well with two effective-dated headers, so the Identity section has a status history
to draw and the class column has codes the registry actually maps.
"""

from datetime import date

from tests.support.seed import seed_well, seed_well_spatial

seed_well_spatial(connection, api10="3305310451", geom_type="surface")  # noqa: F821

for status, effective in (("PR", date(2019, 4, 2)), ("SI", date(2024, 11, 18))):
    seed_well(
        connection,  # noqa: F821
        api10="0512324638",
        effective_from=effective,
        state_code="05",
        county_code_at_permit="123",
        ndic_file_no=None,
        basin=None,
        land_unit_label=None,
        well_name="ECMC CONTROL 1",
        status_reported=status,
        # Null exactly as the Colorado promote writes it: the class is a read-time join.
        status_canonical=None,
    )

connection.commit()  # noqa: F821
