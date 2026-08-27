-- Current-snapshot ND physical-neighbour mart. Geometry is consumed only by the refresh;
-- API reads are indexed scalar joins and never run a spatial function.

create table marts.nd_neighbor_subjects (
    api10                  text primary key check (api10 ~ '^33[0-9]{8}$'),
    completion_date        date,
    formation_id           text,
    formation_group        text,
    formation_status       text not null check (formation_status in (
                               'mapped', 'pool_unavailable', 'alias_unavailable',
                               'below_confidence', 'conflict')),
    formation_pools        text[] not null default '{}',
    formation_month        date,
    lateral_component_count integer not null check (lateral_component_count > 0),
    snapshot_vintage       date not null,
    derivation_id          text not null references lineage.derivations (derivation_id),
    check (
        (formation_status = 'mapped' and formation_id is not null and formation_group is not null)
        or (formation_status <> 'mapped' and formation_id is null and formation_group is null)
    ),
    check (
        (formation_status = 'pool_unavailable' and cardinality(formation_pools) = 0
            and formation_month is null)
        or (formation_status <> 'pool_unavailable' and cardinality(formation_pools) > 0
            and formation_month is not null)
    ),
    unique (api10, snapshot_vintage, derivation_id)
);

comment on table marts.nd_neighbor_subjects is
    'One current ND API-10 with promoted lateral geometry. Completion is the earliest current'
    ' FracFocus job-end anchor; formation is the earliest observed nonblank ND MPR pool set.';
comment on column marts.nd_neighbor_subjects.completion_date is
    'Earliest current hydraulic-fracturing job-end anchor; never spud or first production.';
comment on column marts.nd_neighbor_subjects.formation_status is
    'Explicit mapping result. Null formation fields are unavailable or conflicting, never'
    ' inferred.';

create index nd_neighbor_subjects_formation_idx
    on marts.nd_neighbor_subjects (formation_id, api10)
    where formation_status = 'mapped';

create table marts.nd_neighbor_edges (
    api10             text not null,
    neighbor_api10    text not null,
    distance_m        numeric(14, 3) not null check (
                          distance_m >= 0 and distance_m <= 8046.720),
    distance_epsg     integer not null check (distance_epsg in (32613, 32614)),
    subject_geom_key  text not null,
    neighbor_geom_key text not null,
    snapshot_vintage  date not null,
    derivation_id     text not null references lineage.derivations (derivation_id),
    primary key (api10, neighbor_api10),
    check (api10 <> neighbor_api10),
    check (api10 ~ '^33[0-9]{8}$' and neighbor_api10 ~ '^33[0-9]{8}$'),
    foreign key (api10, snapshot_vintage, derivation_id)
        references marts.nd_neighbor_subjects (api10, snapshot_vintage, derivation_id),
    foreign key (neighbor_api10, snapshot_vintage, derivation_id)
        references marts.nd_neighbor_subjects (api10, snapshot_vintage, derivation_id)
);

comment on table marts.nd_neighbor_edges is
    'Directed current-snapshot physical-neighbour edges through 26,400 ft. Each distance is'
    ' the minimum over every promoted lateral component pair with deterministic geom-key ties.';
comment on column marts.nd_neighbor_edges.distance_epsg is
    'Pair-local UTM zone selected from the EPSG:5070 shortest-line midpoint: 32613 west of'
    ' 102W, otherwise 32614. EPSG:5070 is candidate discovery only and is never served as'
    ' distance.';

create index nd_neighbor_edges_page_idx
    on marts.nd_neighbor_edges (api10, distance_m, neighbor_api10);

grant select on marts.nd_neighbor_subjects, marts.nd_neighbor_edges to glasswell_api;
grant select, insert, delete, truncate on marts.nd_neighbor_subjects, marts.nd_neighbor_edges
    to glasswell_pipeline;
revoke update on marts.nd_neighbor_subjects, marts.nd_neighbor_edges
    from glasswell_pipeline, glasswell_api;
