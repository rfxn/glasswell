- [New] `web/src/chrome/handle.ts` is the one builder for R6's ⌾ derivation affordance, owning
      `EXPLAIN_EVENT`, the button's shape and the accessible contract it carries
- [Fix] The ⌾ handle names the figure it explains before any derivation arrives; the map hover
      card and the thematic key set no `aria-label` until their tile answered, so a screen
      reader met an unnamed button, and both blanked the name again whenever the handle went
      away
- [Change] The derivation id rides `title` rather than the accessible name, so assistive tech
         is read "Lineage for these cell figures" instead of an opaque handle string; the
         handle is visible exactly when it has a derivation to resolve
- [Change] The seven hand-built copies of the affordance — layer panel, legend, hover card,
         thematic key, well card, chart and `<gw-figure>` — are routed through the shared
         builder, with the chart's callback form, the legend's `<label>` cancellation and the
         element's host dispatch kept as declared options rather than private redrafts
- [Fix] `card.ts` registers `<gw-figure>` by an explicit side-effect import; it had been
      relying on a named import for the custom element's registration
