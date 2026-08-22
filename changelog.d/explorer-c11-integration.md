- [New] web/PERF.md records what the frontend costs, measured on the build it describes:
      entry chunk 44,192 B gzipped, the explorer route 62,817 B with the map excluded, the
      map chunk 313,823 B; budgets set from those numbers and enforced by a vitest pin that
      rebuilds rather than reading a possibly-absent dist
- [New] tests/e2e/perf.mjs drives SB-05 §8.5's frame harness over the explorer surfaces at
      ND-scale density; seven interactions, five runs each, 5,346 frames, two dropped and
      none over 100 ms
- [Fix] map: closing a well card that was opened from a deep link, or after a basemap
      change, raised an uncaught TypeError inside MapLibre's render loop and stopped it;
      the selection is now tracked as what was written to the map rather than as what the
      reader picked, and a deep-linked well is highlighted once the style's sources arrive
