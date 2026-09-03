"""Track-local shot fixture for the well card's rail: a surface point on the subject well.

`serve_branch.py` seeds a lateral and no surface geometry, so `surface_point` is null and the
rail's Locate control is absent by its own rule -- correct behaviour, and a posture the visual
gate cannot photograph. Exec'd through `GW_SEED` with `connection` bound.
"""

from tests.support.seed import seed_well_spatial

seed_well_spatial(connection, api10="3305310451", geom_type="surface")  # noqa: F821
connection.commit()  # noqa: F821
