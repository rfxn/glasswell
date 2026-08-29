- [Fix] STATUS.md asserted two deployed versions at once: the header read
      `v0.61+e07db3d` at schema head 52 while the verification state read
      `v0.60+be8e234`; both now read the deployed `v0.62+204bebb` at schema head 54
- [Fix] STATUS.md carried 111 host checks in the P6 row and the verification state;
      the deployed instance passes 127, having read 109 / 18 immediately after the
      deploy with every failure in the Postgres tuning block
- [Fix] STATUS.md read "lease production, well allocation, and its validators are not
      built" for Texas, which buried `canonical.well_lease_links`; the row now states
      that the EWA load populates the Validator A well-to-lease crosswalk and that
      lease production is a registered source with no ingest module
- [Fix] STATUS.md listed land/spacing units among P2's remaining work, conflating no
      JSON endpoint with not built; both ship as tiles and the row now names the five
      published layers and marks `/v1/spacingunits` unserved
- [Change] STATUS.md separates "computed but not served" from "not built" on the
         serving surface: `src/glasswell/modeling/` is 5,211 lines under pinned
         `tcv1.0` / `fv2.0` / `mdv1.4` identities that no router imports
- [Change] STATUS.md records the v0.62 deployment: schema 53 and 54 registering
         publication evidence for `cr_tx_ewa_measures_1` and the three superseding
         API-10 identity rules, the ND neighbour mart at 7,958,550 edge rows over
         22,263 subjects, and CI green on the exact release SHA
- [Change] STATUS.md records the Postgres drop-in applied for the first time — 22
         settings live, `shared_buffers` 2GB→4GB — the 4 GiB swapfile SB-06 §2.3 asked
         for, and that the guest reports 12,179 MB rather than the 16 GiB the drop-in
         was sized against
- [Change] STATUS.md states that the New Mexico OCD staging schema exists and is
         unpopulated, and that the benchmark artifact contract is built with no caller
         outside its own unit test
