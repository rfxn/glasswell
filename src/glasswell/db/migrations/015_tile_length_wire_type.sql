-- ST_AsMVT has no numeric encoding: a `numeric` column leaves the tile as a protobuf *string*
-- carrying twenty significant digits, and a MapLibre expression compares that string
-- lexicographically, where '9000' > '22727' (fp-audit A3-F4). Splitting the column is what
-- keeps both promises: the exact conversion stays in `lateral_length_ft_exact`, where the
-- card-versus-tile equality check (M-2, migration 013) reads it and can still be summed, and
-- the published attribute becomes a double rounded to the cent the card serves.

alter table marts.nd_laterals_tile rename column lateral_length_ft to lateral_length_ft_exact;

alter table marts.nd_laterals_tile
    add column lateral_length_ft double precision;

comment on column marts.nd_laterals_tile.lateral_length_ft is
    'The published tile attribute: the exact conversion rounded to 0.01 ft, as a double, so a
     data-driven style compares numbers. Per feature — summing several of these for one well
     can differ from the card by a cent, which is why the card sums lateral_length_ft_exact.';

comment on column marts.nd_laterals_tile.lateral_length_ft_exact is
    'The conversion glasswell.units computed, unrounded and never published in a tile.';
