- [Fix] The two-clock migration test compared a `published_vintage` PostgreSQL stamps from
      its own `current_date` against the host's `date.today()`, so it reddened on any
      workstation west of UTC for the hours between UTC midnight and local midnight. It
      reads `utc_today()`, the helper added for exactly this, whose docstring already
      described the defect
