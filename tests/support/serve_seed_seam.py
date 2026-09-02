"""GW_SEED for the seam-hardening shots: a registration the neighbour mart does not reach.

`connection` is bound by tests/support/serve_branch.py after the base seeds.
"""
from datetime import date

from glasswell.seed.jurisdictions import REGISTERED_ON, RESTATED_ON
from tests.support.seed import seed_well, seed_well_spatial

CO_API10 = "0512300001"

with connection.cursor() as cursor:  # noqa: F821
    cursor.execute(
        "insert into lineage.jurisdiction_codes values ('CO', 'state') on conflict do nothing"
    )
    cursor.execute(
        "insert into lineage.jurisdictions (jurisdiction_code, effective_from, published_at,"
        " evidence_tag, evidence_commit, name, regulator_name, regulator_url, identity_scheme,"
        " identity_prefix, identity_pattern, source_ids, rationale, neighbors_available,"
        " map_colour, wells_tile_layer_id)"
        " values ('CO', %s, %s, 'v0.78', %s, 'Colorado', 'Colorado ECMC',"
        " 'https://ecmc.state.co.us', 'api10', '05', '^05[0-9]{8}$', array['nd_mpr_xlsx'],"
        " 'planted for the seam-hardening shots', true, '#7C8B96', null)"
        " on conflict do nothing",
        (REGISTERED_ON, RESTATED_ON, "a" * 40),
    )
seed_well(
    connection,  # noqa: F821
    api10=CO_API10,
    state_code="05",
    basin=None,
    spud_date=date(2021, 4, 2),
    operator_name_reported="PLANTED OPERATOR LLC",
    well_name="SEAM 1-2H",
)
seed_well_spatial(connection, api10=CO_API10, geom_type="surface")  # noqa: F821
seed_well_spatial(connection, api10=CO_API10, geom_type="lateral")  # noqa: F821
connection.commit()  # noqa: F821
print(f"planted Colorado registration and well {CO_API10}")
