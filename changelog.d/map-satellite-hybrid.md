- [New] Hybrid basemap: the archive's own road, place and water labels composited over
      satellite imagery, from the PMTiles extract already shipped — no new origin, no key
      and no CSP change, since the label data was always there and no symbol layer was ever
      constructed on the raster path
- [Change] Satellite imagery now reads from Esri World Imagery rather than USGS National
         Map, a swap and not an addition, so exactly one external origin stays named in the
         policy; measured, USGS serves nothing above z16 while the map reaches z18, so every
         z17-z18 view was a z16 tile stretched 4x
- [Change] The imagery source declares `maxzoom` 19 because that is the deepest level both
         basins in scope were measured to carry, not because the service stops there: the
         deepest level with real pixels ranges z17 to z20 by location and is not monotonic,
         so a region added later has to be re-probed rather than inheriting 19
- [Change] The map's own `maxZoom` rises from 18 to 19 to reach the level the imagery now
         serves, halving ground resolution to 0.2 m per pixel in both basins; a test holds
         it equal to the imagery ceiling, since below it a served level is unreachable and
         above it the map paints the service's grey placeholder with no error anywhere
- [Change] Every basemap option declares the substrate it is read against instead of having
         one inferred from its id; an option whose id is not a variant name used to resolve
         silently to the dark token row, which is slate labels over bright aerial
- [New] The hybrid's two substrates fail independently and are named separately: imagery
      unreachable keeps the labels and names the imagery host, an archive that cannot serve
      ranges degrades to the graticule and names the archive
- [Fix] The imagery credit is dropped together with the imagery it covers, so an attribution
      never renders over a canvas with nothing of that source drawn on it; the hybrid probes
      the origin before drawing either, and reports the loss from the resolve path, because
      a source that was never added raises no tile error for the banner to read
