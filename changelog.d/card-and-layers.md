- [New] map: the layer list is grouped by what a layer is of rather than by the mart that
      publishes it. Well spine, land and legal framework, derived surfaces and geology
      framework each head a collapsible band; a band opens when the reader is already
      drawing something inside it and carries a count of its live switches when shut, so
      nothing on the canvas is hidden without a mark. The panel now fits above the fold at
      every breakpoint, 635px of list at 390 wide becoming 419px
- [New] map: a layer that is switched on, in scale, and painting nothing at this extent
      says so on its own row instead of looking drawn. Read off the canvas at map idle, so
      a layer whose tiles are still streaming is never reported absent; the wording states
      the canvas and never the ground, because a failed source queries empty too
- [New] card: the well header carries the status as the same glyph the map painted it
      with, and names the code the regulator filed beside the canonical class, so the
      mapping is readable rather than hidden. Loaded on a dynamic edge, which is what keeps
      the map status vocabulary off the entry chunk and off the explorer route
- [Change] card: the well facts read as four bands, operator, location, drilling and
           completion, and record, instead of one flat list where a compute CRS carried the
           same weight as the operator; a band whose every field is absent is dropped
           rather than left heading an empty list
- [Fix] card: an absent value is no longer typographically identical to a measured one.
      DR-H24 recorded that absence and measurement shared colour, weight, family and font
      style, and that this becomes a real problem when a panel is skimmed rather than read;
      absence now takes one muted italic form and still names which kind of absence it is
- [Fix] card: the neighbour rows printed the raw null-semantics token, so "alias
      unavailable" stood in the Formation cell looking exactly like a formation name beside
      "bakken". Both the absent value and the mapping state are spelled out now, each from
      its own endpoint's vocabulary, which are rendered in one form and never asserted to
      mean the same thing
- [Change] tests/e2e/chrome-fold.mjs: the fold arithmetic divides by rendered rows and
           asserts every group header is reachable, plus every operable layer having a row
           at all. A row inside a shut group has a zero rect, which would have made both
           the fold count and the mean row height pass while measuring nothing
