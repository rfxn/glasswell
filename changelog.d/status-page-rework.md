- [New] Status serves a Deployment block: code version, schema head, edge host,
      database storage, and the posture the serving process is actually enforcing
      (public origin, anonymous reads, tile upstream, frontend bundle, local
      basemap, CSP), read from the API process rather than the snapshot because
      only it knows what it refuses
- [New] Status groups components into an Architecture section by tier — serving
      plane, data plane, edge, host — and names the systemd unit or mount each one
      was observed through, so a reader can act on the row
- [New] The collector observes the Cloudflare tunnel (`cloudflared.service`), the
      status-snapshot timer that writes this page, and the Cloudflare range
      refresh; three components the deployment ran with no telemetry at all
- [New] Scheduled work reports each job's timer unit and whether it is armed,
      separately from whether its last run succeeded
- [New] Dataset inventory counts `lineage.conformance_rules` — registered rules,
      rules in force today, rule families, sources covered — so R8's mapping
      registry has a magnitude on the page
- [New] Open quarantine is inventoried per reason code as well as in total; the
      per-reason metrics partition the open population
- [New] Monthly production carries a distinct-month count per state alongside its
      span, because two endpoints cannot show a hole between them
- [New] Status discloses that staging is not inventoried, rather than leaving its
      absence to inference
- [Change] Dataset inventory becomes a Data footprint table grouped by storage
           layer (canonical, marts, lineage), with scope, grain, magnitudes, the
           span covered and latest knowledge on one scannable row; each dataset's
           served caveat and count time move into a per-row disclosure
- [Change] Method statements that qualified a section rather than reported its
           state — what a check proves, how counts are grained, what a run time
           means, how freshness is decided — move from standing paragraphs into
           collapsed disclosures beside each heading; visible standing prose on the
           surface drops from 276 words to 77, all of it served content
- [Change] Precision is marked once per footprint row when every metric shares it
           and per metric when they differ, replacing a badge on all 43 counts
- [Change] Component cards state their observation time only when it differs from
           the snapshot's, instead of repeating one timestamp on every card
- [Change] The committed OpenAPI snapshot regains the served document: `deployment`,
           `checks[].tier`, `checks[].probe`, `jobs[].unit`, `jobs[].timer_armed` and
           `platform.edge_host` are all additive
- [Change] `tests/e2e/status-surface.mjs` grows from 88 to 124 assertions, adding
           deployment facts, tier grouping and probe identity, layer grouping and
           laid-out magnitude height, a derivation handle on every rendered count,
           and that each demoted caveat starts collapsed behind a visible control
           and becomes visible when opened; visibility is measured with
           `checkVisibility()`, since a closed `<details>` keeps a laid-out box that
           makes both `getBoundingClientRect()` and `offsetParent` report it visible
