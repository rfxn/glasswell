- [Fix] map: a tile or count refused for want of a session is a normal state, not a
      failure; 401/403 raises no banner, no toast and no console error, and signing in
      re-requests every data source and re-asks the counts, so the false "Tiles for
      nd_wells did not load" and "Well counts unavailable" no longer outlive the sign-in
      that answers them
- [Fix] sign-in now updates the header and session state from the session the login panel
      returns; the boot probe had already latched, so a signed-in reader was still shown
      as signed out
- [Change] login copy greets the reader and says what is behind the door, instead of
           describing what the deployment refuses; refusal messages still enumerate no
           accounts
- [Change] em dashes are out of user-facing copy: page title, share-card metadata, panel
           and banner text, empty and error states now read with a colon, comma or full
           stop; the absent-value mark and console diagnostics keep theirs
- [Change] report vintage moves off the default reading surface into a closed disclosure
           on the chart, and the "mixed report vintages" warning chip is gone; the fact is
           routine provenance, the derivation handle beside it is untouched, and the
           disclosure is re-read over the drawn window so it cannot claim a vintage the
           span dropped
