- [Fix] Well card, monthly production: the ND back-load took this well's axis from
      6 months to 131 and the chart was designed against 6. One month's tap target
      measured 2 CSS px across — three rows of 131 buttons sharing 426 px — so the
      state a reader wanted could not be hit, and three streams at 131 points over
      426 px drew a scribble
- [New] The pointer now resolves to the month nearest it across the whole plot
      rectangle and the whole state band, one hit surface instead of 393, and the
      month it lands on is read out below the plot: every stream's volume, unit,
      report state, report vintage and its own derivation handle. The handle and
      the month stepper are 44 px targets, and the stepper is the keyboard path a
      canvas hover never had
- [New] A range control on the card's chart — 1 year, 2 years, 5 years, All —
      offered only where the record is longer than the span, so a well with six
      months is never asked to choose between two identical charts. Nothing is
      aggregated, binned or downsampled to fit: the window is a view over the
      served series, every drawn point is one month at its own value, and widening
      it costs no request
- [New] The card states the window it is drawing — "showing 60 of 131 months on
      record", both ranges, and that the rest is one click away. A chart showing
      part of a record while implying it shows the record is a naked number wearing
      a time series (R6)
- [Change] The default window is anchored on the last month on record rather than
         on today, so a well that stopped producing in 2015 draws its own last five
         years instead of an empty chart, and it windows by calendar span, so a
         gappy record reports the months it actually holds in that span rather than
         the span's length
- [Change] The four report states are drawn as one band per stream aligned under
         the plot rather than a row of buttons beside a label: it starts and ends
         where the plot area does, measured off the plot rather than assumed, and a
         reported zero is a bar of zero height inside its own cell, which survives
         at five pixels where a hollow outline did not
- [New] "Open this series" lands on the plot as well as the rows: the explorer
      redraws the series at the panel's width, 760 px against the card's 426, from
      the response the grid already fetched, with the same month readout and the
      same handles. Its window is the stream, from and to facets, which ride the
      URL, so the plot grows no second control a shared link would not carry
- [New] A collection whose operation declares a sort order can be reversed on the
      explorer, offered only where the server has no next page to give — a
      descending page one whose next link walks the ascending order would be a claim
      the collection does not make. The direction rides the URL, and is absent from
      it while it is the server's own
- [Fix] The series' own warnings, including the series_spans_derivations line
      naming the derivations behind a column, moved out of the element the chart
      replaces; a span change or a theme repaint used to take R8's disclosure down
      with the plot it had been appended to
- [Fix] Each chart repaint left its predecessor's resize observer and theme
      listener alive, so a surface redrawn N times observed and rebuilt N times.
      One live chart per host now, and the old one is torn down before the new one
      is built
- [Change] The card loads the chart on demand rather than from the entry chunk, so
         uPlot no longer ships to every reader whether or not a card is opened; the
         entry chunk falls from 46,330 to 21,340 B gzipped
- [Change] The bundle budgets are re-measured against that split: the entry falls
         to 22,500 B and the explorer route rises to 71,500 B, both at the ~5%
         headroom the convention in `web/PERF.md` states
