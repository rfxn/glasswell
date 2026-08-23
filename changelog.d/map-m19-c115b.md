- [New] NM OCD C-115B natural gas waste capture (M1-9): glasswell/ingest/nm_c115b.py
      walks the well-level flaring and venting layer through arcgis_rest_paginate,
      preserves the assembly as one manifested raw artifact, and loads
      staging.nm_c115b_upstream; migration 036, staging terminus by design
- [New] glasswell-c115b.service and .timer, monthly on the 12th with Persistent=true;
      reporting_period is a rolling ~13-month window and a month that rolls out is
      unrecoverable from the endpoint, so a missed fire is caught on the next boot
- [New] five conformance rows for nm_c115b_upstream: source selection over the stale
      OCDView/Venting_Flaring demo layer, the walk order, the dashed-API-10 to API-10
      normalisation, the F/V waste vocabulary in lineage.nm_waste_type_map, and the
      NAD83 to EPSG:4326 transform
- [Fix] arcgis_rest_paginate walked every layer ordered by OBJECTID, which the C-115B
      layer assigns per query rather than storing; a resultOffset walk over it re-read
      and skipped rows while count_before, count_after and features_written all
      reconciled. Callers may now declare a stable total order; the default is
      unchanged, and a repeated identity key inside one harvest quarantines as
      duplicate_row
- [Change] infra/verify.sh asserts every glasswell-* unit in the tree is installed and
           byte-identical to it, so a unit added to infra/systemd but not to
           install.sh's placement loop fails verification instead of silently never
           running
