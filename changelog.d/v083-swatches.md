- [Fix] the layer panel's two status-keyed line swatches — Laterals and Well paths — are drawn
      from the served status vocabulary instead of the empty store the panel is built against:
      every row redraws its mark in the same `/v1/jurisdictions` response its count already
      waits on, so the rows the map paints from `statusColourExpression()` carry the domain's
      leading and trailing class colours rather than transparent (v0.83 visual gate M1)
