- [New] map key: wells by reported well type and by geometry provenance, two
      dimensions /v1/wells/status-summary already served and the client discarded;
      every row is a served figure with its own derivation handle, the provenance
      block states that its classes overlap and do not sum, and each block is a
      disclosure under the key's scroll body rather than inside it, so neither it
      nor the cross-reference to the other scope has to be scrolled to be found
- [New] map: a Wells by sheet beside the layer panel, counting every current well
      in one state rather than the map view and saying so on screen; each panel
      carries a one-line cross-reference to the other scope
- [New] map: pressing a bucket narrows the canvas to that value across every well
      and bore layer, including the five whose filter slot is not the status
      gate's; the applied bucket rides the URL as wb.pick, and back and forward
      move the pill, the pressed row and the canvas filter with it
- [New] map: an applied-bucket pill carrying the panel's own figure and handle,
      never a count of the canvas; it names the layers a press does not reach,
      states that the tiles keep one well per half pixel below zoom 8, and paints
      on --panel so the filter it announces is readable in either theme
- [Change] the Wells-By panel takes its applied filters, its press rule and its
         scope line from its host, so the map and the explorer render one
         component rather than two; it drops its rank and bar columns on its own
         column width rather than the window's, and states on screen rather than
         in a tooltip alone where the surface cannot be narrowed by a dimension;
         the explore surface is unchanged
- [Change] the wells dataset declares geometry_provenance as a facet, so a
         crossing onto that filter renders a chip the reader can clear
- [Change] the layer panel and the Wells by sheet share one frame declaration,
         .gw-sheet; opening either shuts the other, Escape closes whichever is
         open and hands focus back to the control that opened it, and at 768 and
         under the drawer clears the map's own control column
- [Fix] map key: the ⌾ on a producing or dimension row is a control rather than
      the key's expand target, so asking where a count came from no longer
      collapses the key and throws away the scroll position that reached it
- [Fix] map key: the rule between the key's groups is a defined token that
      follows the panel's substrate, not an undefined one falling back to a white
      that measured 1.00:1 against a light basemap's white panel
- [Fix] map key: the key is capped at the map's own height less its insets and
      lays its blocks out as a column, so opening both dimension blocks on a
      phone no longer grows it off the top of the map and under the app header —
      where a tap aimed at the title that collapses it landed on the surface
      switch and navigated the reader off the map
