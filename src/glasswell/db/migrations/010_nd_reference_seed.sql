-- Reference data the ND rules resolve against. Pure data: every table already exists.

insert into lineage.crs_registry (basin, compute_epsg, storage_epsg, effective_from, note)
values ('williston', 32614, 4326, date '2026-01-01',
        'UTM 14N; every ND distance, area and spacing computation runs projected, never in degrees')
on conflict do nothing;

-- Counts are the measured frequency in OGD_Wells.dbf (43,812 records) at planning time.
-- The permit-lifecycle terminal states collapse to expired; see rule cr_nd_status_vocab_1.
insert into lineage.nd_status_map (status, status_canonical, confidential)
values ('A',            'active',                 false),   -- 20640
       ('PA',           'plugged',                false),   --  6447
       ('DRY',          'dry',                    false),   --  6347
       ('PNC',          'expired',                false),   --  5725
       ('IA',           'inactive',               false),   --  1597
       ('Confidential', 'confidential',           true),    --   962
       ('AB',           'plugged',                false),   --   842
       ('LOC',          'permitted',              false),   --   610
       ('DRL',          'drilling',               false),   --   340
       ('TA',           'temporarily_abandoned',  false),   --   174
       ('TAO',          'temporarily_abandoned',  false),   --    30
       ('PANF',         'plugged',                false),   --    27
       ('EXP',          'expired',                false),   --    22
       ('PNS',          'expired',                false),   --    20
       ('TASC',         'temporarily_abandoned',  false),   --    11
       ('TATD',         'temporarily_abandoned',  false),   --     8
       ('NC',           'drilling',               false),   --     7
       ('LOCR',         'expired',                false),   --     2
       ('NJ',           'inactive',               false)    --     1
on conflict do nothing;

-- GasSold and Flared are dispositions of produced gas, not streams. They carry no canonical
-- value, so the promotion frame quarantines them with a reason and C7 becomes measured.
insert into lineage.nd_stream_map (stream_raw, stream_canonical, promoted)
values ('Oil',     'oil',   true),
       ('Wtr',     'water', true),
       ('Gas',     'gas',   true),
       ('GasSold', null,    false),
       ('Flared',  null,    false)
on conflict do nothing;
