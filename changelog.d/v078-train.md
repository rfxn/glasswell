- [Fix] The scheduler's double-run guard reported a DSN psycopg could not parse as a
      double-run hazard rather than as a check that never ran, because it caught
      `psycopg.OperationalError` where a malformed connection string raises
      `psycopg.ProgrammingError`
