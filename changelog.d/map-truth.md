- [Fix] app/router: the Map → Explore crossing narrows the wells collection by
      `api10`, the parameter that names the row, instead of by `q`, which
      `/v1/wells` accepts as a `well_name` substring and answers with nothing
      for every API-10 a reader had selected
- [New] map: Basins and Plays rows in the Geology framework group, drawn from
      `marts.basin_boundaries_tile` — the EIA lower-48 boundaries this build has
      ingested, served and allowlisted since migration 063 — with a `geology`
      line role and per-variant token so the frame is recoloured for the
      substrate under it and never reads as an administrative boundary
- [Remove] map: the `play-outline` and `geology-au` stub rows and the
           `pendingSource` vocabulary behind them; the first promised work that
           had already shipped, the second promises work nothing serves
- [Change] main: one latched session probe, awaited immediately before the map
           and explorer mounts, so a signed-out first paint no longer spends a
           403 on every tile source and the status summary behind the login
           modal; `/basemap/*` stays anonymous and the expiry suppression in
           `map.ts` is unchanged
- [New] map: a `minZoom` of 3 and a `maxBounds` holding the contiguous
      forty-eight, mainland Alaska, Canada and Mexico, so a pinch or a drag can
      no longer leave the reader over an empty world with every tile source
      still fetching
- [New] web: `test:changed` and `test:watch` scripts for the narrow loop, with
      `test` left as the full suite CI runs
