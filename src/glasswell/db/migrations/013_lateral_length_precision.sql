-- The tile mart stores the conversion, not a rounding of it (M-2). numeric(12,2) rounded every
-- lateral independently, so summing three of them drifted from the figure the API serves for
-- the same well: 6731.13 against 6731.12 ft for api10 3300701202. Rounding happens once, at
-- the serving edge; the mart carries what glasswell.units computed.

alter table marts.nd_laterals_tile alter column lateral_length_ft type numeric;

comment on table marts.nd_well_card is
    'Created for the card endpoint and deliberately never written: the API reads canonical
     directly (PLAN.md M6). It has no writer on purpose — do not go looking for one.';
