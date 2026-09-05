- [New] The canonical well-status class domain is a registry table: twelve rows in
      `lineage.status_classes` under `cr_status_class_domain_1`, each carrying its label,
      colour, glyph, `min_zoom`, legend order and a jurisdiction-neutral note, with a foreign
      key from every registered status map so the set a regulator maps onto is a domain rather
      than a sixth copy computed at query time
- [New] `/v1/jurisdictions` serves each registration's status vocabulary, its legend note, the
      seven presentation facts the registry already held and the domain once in `meta`, and the
      map builds its legend, symbology, zoom gate and filter from that one response
- [New] No well anywhere is served a null status class: a well whose source filed no code
      resolves to the absence class, the filed code is served beside it as what says whether the
      source reported none or the vocabulary had no row, and `?status=` matching that class
      returns the wells the legend counts
- [New] Montana's production grain is a registered decision (`cr_mt_bogc_pool_rollup_1`), so the
      389 API-10s whose series is a disclosed sum name the rule that says so, link to their pool
      filings and carry an aggregation warning
- [New] New Mexico's per-well series is served as a sum over its completion-pool filings from
      `marts.well_pool_rollup` under `cr_nm_wcproduction_pool_rollup_2`, with every point
      resolving to the refresh that produced it, a warning that says it is a sum, and a link
      down to the filings it was summed from
- [Change] `?as_of=` is refused rather than answered on New Mexico's summed well series, with
           the rule, the reason and the pool surface that does answer it named in the problem
           detail: the rollup mart holds one snapshot per key, so an older date would be
           answered with today's sum wearing the caller's date
- [Change] The read-time status resolver attaches its own refresh trigger to every registered
           map through `lineage.attach_status_map_refresh()`, so a fifth read-time jurisdiction
           is three registry rows and no migration; Colorado, which registered read-time
           resolution in v0.78 and shipped with no trigger on its map, gets one on this deploy
- [Change] The resolver resolves the registry at the registry's own knowledge cut rather than at
           the host's calendar, which is the clock the API reads, and `infra/verify.sh` compares
           the two and asserts no jurisdiction loses a serving rule row between them
- [Change] `/v1/wells/status-summary`'s `unmapped_wells` is predicated on the class the absence
           arm gives rather than on the filed code, so it keeps the population its three field
           descriptions describe, and the served OpenAPI prose carries no count
- [Fix] The disposal hover, the injection codebook and the geometry-provenance legend note name
      the feature's own regulator and its own rule, or say that none is registered, where all
      three said "as ND filed it" whatever the well
- [Fix] Every wells tile mart reads the one status resolver, so a promotion-time jurisdiction's
      tile no longer carries a null for a well the API had already given a class, which is what
      made pressing the absence class in Wells By show `Showing 0 of N`
- [Fix] The absence class and `expired` are repainted to clear the 3:1 non-text contrast floor
      on all four substrates a swatch is read against, and the floor and the three classes that
      do not clear it on the light theme are published on the domain's own rule
- [Fix] A narrow month window no longer tells a well with a well-level series that its regulator
      files per completion pool and glasswell performs no rollup
- [Fix] The pool-grain disclosure is chosen from the well rather than from its jurisdiction's
      registration: a well the sum admits no filing of keeps the panel and the link down to its
      filings, and a well that filed nothing below it is told of no sum at all
- [Fix] A summed month whose pool filings were all explicit zeros is served as `reported_zero`
      and a stream with no filing in a served month as `no_report`, where both read as
      `reported` and as a null; each point carries its own month's report vintage rather than
      the whole well's maximum
- [Fix] A summed month the rollup admits no filing of is served `withheld` only where the
      filings themselves say so, and `no_report` otherwise, where the token was inferred from
      the sum admitting none of them — a word New Mexico's pools never file
- [Fix] `?normalization=per_lateral_ft` is refused on the summed series for the reason the
      allocated arm gives, where it was accepted and silently ignored
- [Fix] Unticking a status class on the map takes its strike off the canvas with it: the struck
      overlay keeps its own set of terminal classes and the status gate now narrows that set,
      where a press left the strike painted over the mark it had just removed for `dry` and
      `plugged` on every registered jurisdiction
- [Fix] Production by pool says the series above it is glasswell's sum of the filings on a well
      the rollup serves, where it told every pool-grain well that nothing rolls up and no sum is
      served — the opposite of the chart drawn above it, under the same rule id
- [Fix] The well card opens Production by pool on whether the regulator filed below the well,
      not on whether a sum is missing, so a well the rollup mart serves keeps both its summed
      chart and the section holding the filings that chart is a sum of
