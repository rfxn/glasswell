-- The neighbour mart stops being single-state. ND wells within 26,400 ft of the Montana line
-- have offsets on the Montana side, and a subject set constrained to '^33[0-9]{8}$' truncated
-- their neighbour lists without saying so — ROADMAP open question #11's worked example, and a
-- correctness gap rather than a coverage one.
--
-- The table names keep their nd_ prefix. Renaming them is a serving-contract change touching
-- the router, the selector registry, the status collector and the OpenAPI snapshot, and it is
-- not smuggled in behind a scope widening.

alter table marts.nd_neighbor_subjects
    drop constraint nd_neighbor_subjects_api10_check,
    add constraint nd_neighbor_subjects_api10_check
        check (api10 ~ '^(25|33)[0-9]{8}$');

alter table marts.nd_neighbor_edges
    drop constraint nd_neighbor_edges_check1,
    add constraint nd_neighbor_edges_check1
        check (api10 ~ '^(25|33)[0-9]{8}$' and neighbor_api10 ~ '^(25|33)[0-9]{8}$');

-- The zone is computed from the pair-local midpoint rather than picked from a pair, so the
-- admitted set is the zones the supported domain can produce. Montana reaches UTM 11N; the
-- previous binary choice had no unsupported branch at all, so a pair outside 13N/14N was
-- silently measured in one of them and stored under a handle claiming a pair-local CRS.
alter table marts.nd_neighbor_edges
    drop constraint nd_neighbor_edges_distance_epsg_check,
    add constraint nd_neighbor_edges_distance_epsg_check
        check (distance_epsg in (32611, 32612, 32613, 32614));

comment on constraint nd_neighbor_edges_distance_epsg_check on marts.nd_neighbor_edges is
    'UTM zones the supported longitude domain (-116.10 .. -96.50) can produce. A zone outside'
    ' the set is a geometry the domain guard should already have refused, so this fires loudly'
    ' rather than persisting a distance measured far off its central meridian.';

comment on constraint nd_neighbor_subjects_api10_check on marts.nd_neighbor_subjects is
    'North Dakota (33) and Montana (25). Widening this is what repairs the truncated'
    ' neighbour sets on the ND side of the Williston; see marts/neighbors.py STATE_CODES.';
