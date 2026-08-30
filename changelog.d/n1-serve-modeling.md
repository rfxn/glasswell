- [New] api: GET /v1/wells/{api10}/type-curve serves the pinned tcv1.0 control for one
      held-out test subject — P10/P50/P90 monthly and cumulative curves month-indexed to
      the split's horizon, both normalisation arms, the resolved peer-ladder rung, the
      per-month peer support and the cum12/cum24 band; every array carries a handle that
      resolves to the pinned artifact and its split set at the default explain depth
- [New] api: control_unavailable is a served outcome on a required field — a 200 naming
      its reasons with the figure slots present and null, whose handles resolve to the
      rung that terminated rather than to a value that does not exist
- [New] api: GET /v1/type-curves browses the control population at its horizon with the
      ladder rung, the control_unavailable reasons and the per-subject peer support,
      cursor-paginated and rate-limited; the two support columns are page-level series,
      so a page mints two evidence rows rather than two hundred
- [New] api: GET /v1/modeling/publications and its detail serve the accepted P3
      publication receipt — the three semantic versions, the three pinned derivations,
      the split set and every split hash, the acceptance gates with their thresholds, and
      the peer-ladder support distribution; a second publication is announced as a
      restatement with the prior one linked and still addressable
- [New] modeling: served.py resolves the control through four independent agreements — an
      accepted publication receipt, a registered typecurve.build derivation,
      receipt/locator/digest agreement, and a containment-checked non-symlink path whose
      sha256 matches output_sha256 — and re-stats the file after the read
- [New] seed: five code_ref conformance rules record the type-curve serving decisions —
      which publication is servable, the closed peer ladder, what typecurve_per_kft
      rescales to, that quantiles are statistical-ascending and not the reserves reading,
      and that control_unavailable is a stated value
- [New] seed: glossary terms for quantile convention, peer ladder and split set
- [New] infra: GLASSWELL_MODEL_ROOT pins the registered artifact tree the API may read;
      unset refuses every type-curve route rather than reading an unregistered path
- [Fix] api: the served control is resolved through the receipt keys the P3 builder writes,
      artifact_sha256.typecurve_control and .typecurve_coverage, not the artifact_uri
      vocabulary; the two key spaces are now named once in p3_publication and imported by
      every consumer, and the contract fixture derives its receipt from them
- [Fix] api: an empty facet value on the type-curve index is an unset filter rather than a
      second response identity; it minted one derivation for two pages, and a derivation
      row is immutable, so one request poisoned the default page permanently
- [Fix] api: the type-curve index pages by the subject instance rather than by the api10,
      so a subject held out at more than one origin keeps its rows at a page boundary
- [Fix] web: a label column declared as a series projection rendered as a figure with no
      handle; the type-curve grid carried twenty-eight naked-number badges and now carries
      none, and the control_unavailable reasons are a default column
- [Fix] web: a composite row identity is addressable by a detail operation whose single
      path parameter names one of its pointers, so the type-curve detail pane opens
      instead of reporting that the row supplies no value for it
- [Fix] web: a nested block whose leaves are figures renders as figures rather than as a
      pre block of its JSON, so the publication receipt's acceptance gates and support
      distribution are explain affordances rather than printed handles
- [Change] api: register_response_figures walks and rebinds Series alongside Figure,
         recording the whole array and its unit as selector evidence; a series without a
         selector, or one carrying point handles, is refused rather than silently skipped
- [Change] api: unregistered_artifact drops emitted=false in the phase that first raises
         it, and the served description states the control is a backward-looking peer
         aggregate over a held-out arm rather than a forecast
- [Change] docs: STATUS, ROADMAP, ARCHITECTURE, README and SMOKE record N1 as served, the
         chain-depth headroom the contract tier cannot measure, and a re-publication of
         the P3 context as a restatement event
