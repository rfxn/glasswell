- [New] map key: wells by reported well type and by geometry provenance, two
      dimensions /v1/wells/status-summary already served and the client discarded;
      every row is a served figure with its own derivation handle, and the
      provenance block states that its classes overlap and do not sum
- [New] map: a Wells by sheet beside the layer panel, counting every current well
      in one state rather than the map view and saying so on screen; each panel
      carries a one-line cross-reference to the other scope
- [New] map: pressing a bucket narrows the canvas to that value across every well
      and bore layer, including the five whose filter slot is not the status
      gate's; the applied bucket rides the URL as wb.pick and the back button
      undoes it
- [New] map: an applied-bucket pill carrying the panel's own figure and handle,
      never a count of the canvas; it names the layers a press does not reach and
      states that the tiles keep one well per half pixel below zoom 8
- [Change] the Wells-By panel takes its applied filters, its press rule and its
         scope line from its host, so the map and the explorer render one
         component rather than two; the explore surface is unchanged
- [Change] the wells dataset declares geometry_provenance as a facet, so a
         crossing onto that filter renders a chip the reader can clear
- [Change] the layer panel and the Wells by sheet share one frame declaration,
         .gw-sheet, and Escape closes whichever of them is open
