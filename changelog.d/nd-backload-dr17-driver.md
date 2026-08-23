- [Fix] DR-17: infra/load-nd-months.py no longer writes a vintage row of its own at
      the end of the walk — ingest_month's record_vintage_day already checkpoints the
      knowledge-day row after every month, so the driver's union overwrote accumulated
      counters and, on a walk that crosses UTC midnight, filed both days under the last
      one; the summary now reads the ledger back instead of reporting from memory
- [New] the back-load driver survives an unattended multi-hour run: --resume skips
      workbooks already staged for this source (asked of lineage.manifests and
      staging.nd_mpr_oil, not a state file), --log-file appends every progress record
      to a file that outlives a dropped ssh session, and --raw-root states in the log
      where the fetched bytes landed rather than inheriting a CWD-relative default
- [Fix] one unreachable or malformed workbook no longer ends the walk: the month is
      rolled back, reported with its error on the progress stream, and the remaining
      months continue, with a non-zero exit naming what failed
- [Fix] SIGTERM and SIGINT stop the back-load at a month boundary rather than mid
      transaction — the polite pause waits on an event, which a signal clears, instead
      of time.sleep, which PEP 475 restarts for the remainder of the interval
