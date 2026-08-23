- [New] Hybrid basemap: the archive's own road, place and water labels composited over
      satellite imagery, from the PMTiles extract already shipped — no new origin, no key
      and no CSP change, since the label data was always there and no symbol layer was ever
      constructed on the raster path
- [Change] Satellite imagery now reads from Esri World Imagery rather than USGS National
         Map, a swap and not an addition, so exactly one external origin stays named in the
         policy; measured, USGS serves nothing above z16 while the map reaches z18, so every
         z17-z18 view was a z16 tile stretched 4x
- [Change] The imagery source declares `maxzoom` 19, the last zoom that carries pixels,
         rather than the 24 levels the service advertises: z20 is a byte-identical grey
         "no data" placeholder at every location probed across both basins
- [Change] Every basemap option declares the substrate it is read against instead of having
         one inferred from its id; an option whose id is not a variant name used to resolve
         silently to the dark token row, which is slate labels over bright aerial
- [New] The hybrid's two substrates fail independently and are named separately: imagery
      unreachable keeps the labels and names the imagery host, an archive that cannot serve
      ranges degrades to the graticule and names the archive
- [Fix] The imagery credit is dropped together with the imagery it covers, so an attribution
      never renders over a canvas with nothing of that source drawn on it
