- [Fix] The scheduler's double-run guard reported a DSN psycopg could not parse as a
      double-run hazard rather than as a check that never ran, because it caught
      `psycopg.OperationalError` where a malformed connection string raises
      `psycopg.ProgrammingError`
- [Fix] A Colorado production row the promotion quarantined recorded every staged SQL null in
      `lineage.quarantine_rows.row_payload` as the four characters `None`, so a blank the
      regulator filed could not be told from a column filed with that text
- [Change] The `cursor_query_mismatch` refusal says what to do when the filter a reader did not
           change is `?state=all` and a jurisdiction registered mid-traversal
