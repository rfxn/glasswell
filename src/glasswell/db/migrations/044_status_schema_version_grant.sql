-- The unprivileged Status collector reports the applied migration head. The bootstrap table
-- lives in public and predates the runtime-role grants, so expose only its read surface.

grant select on public.schema_migrations to glasswell_api;

comment on table public.schema_migrations is
    'Append-only migration ledger; runtime API access is read-only for status reporting.';
