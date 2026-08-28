-- Support the reverse subject foreign key and keep full current-snapshot replacement bounded.
-- PostgreSQL does not create indexes on the referencing side of a foreign key automatically.

create index nd_neighbor_edges_reverse_fk_idx
    on marts.nd_neighbor_edges (neighbor_api10, snapshot_vintage, derivation_id);
