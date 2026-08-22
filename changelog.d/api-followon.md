- [New] well_type filter on /v1/wells: matches the code exactly as the regulator
      filed it, no decode and no classing, so the disposal layer's class can scope
      the spine; composed into the cursor fingerprint, so a cursor minted under one
      well_type is refused under another instead of quietly re-scoping the page
- [Change] the status-summary handle count now rides the envelope's own walker
         instead of a router-local duplicate, and a hand-authored explain link is
         refused even when it smuggles its handle in a URL fragment
