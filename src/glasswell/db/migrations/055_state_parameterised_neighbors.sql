-- Migration 045 wrote North Dakota's API-10 prefix into three check constraints, so a second
-- state's neighbour row could not be represented at all. The widening lands before any non-ND
-- row exists rather than after, because a check constraint is a migration and a served spacing
-- or parent/child figure built under the narrow one would have to be restated.

alter table marts.nd_neighbor_subjects
    drop constraint nd_neighbor_subjects_api10_check;
alter table marts.nd_neighbor_subjects
    add constraint nd_neighbor_subjects_api10_check check (api10 ~ '^[0-9]{10}$');

alter table marts.nd_neighbor_edges
    drop constraint nd_neighbor_edges_check1;
alter table marts.nd_neighbor_edges
    add constraint nd_neighbor_edges_api10_check
        check (api10 ~ '^[0-9]{10}$'
           and neighbor_api10 ~ '^[0-9]{10}$'
           and left(api10, 2) = left(neighbor_api10, 2));

comment on constraint nd_neighbor_edges_api10_check on marts.nd_neighbor_edges is
    'An edge stays intra-state after the prefix widening: distance is measured in a pair-local'
    ' UTM zone chosen from the pair midpoint, and that choice is undefined across an arbitrary'
    ' state pair.';
