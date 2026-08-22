- [Fix] web: the header as_of chip honours a pinned route at boot — a reader
      arriving on ?as_of= sees their own pin beside the knowledge-time control
      instead of the latest published vintage, so the two claims agree on
      multi-vintage deployments; unpinned routes keep today's behaviour
      (gate-c12 R5, visual F3; approved frozen main.ts edit under CADENCE §2.2)
- [Fix] map: the layer crossing's off-state title names its true cause — an
      unticked Map view node says the toggle widened the box, and only a
      genuinely too-wide viewport blames the view's width (gate-m12 F1)
- [Fix] map: the extent row's tooltip flips with the node — in-view coverage
      while it is on, everything ingested while it is off — instead of
      asserting in-view coverage in both states (gate-m12 F2)
- [Fix] web: the vintages facet test derives its control list from the committed
      snapshot instead of a hand-written copy, so v0.27's additive explain and
      explain_depth parameters no longer redden the suite
