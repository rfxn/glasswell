- [Change] app chrome no longer hardcodes a coverage footprint: the page title is
         `glasswell — subsurface well intelligence`, the map's aria-label names laterals
         and surface locations, and the help panel and the OpenAPI `info.description`
         point at `/v1/status` dataset scope instead of restating a two-state string
- [Change] collateral de-scoped to match: the README hero badge reads coverage
         multi-basin and its opening paragraph drops the two-regime ceiling, `llms.txt`
         opens on reporting regimes rather than a basin list, and the og-card subtitle
         carries the capability line
- [New] `og:` and `twitter:` meta tags wired to the existing share card, so a link
      unfurl renders `og-card.png` at 1200x630 instead of falling back to the title
- [New] regression assertions pin the page title, the share-card tags, and the absence
      of any place name in the document head or the map's label
