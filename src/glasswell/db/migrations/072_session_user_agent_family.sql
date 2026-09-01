-- A coarse client label for the session list, written when the session is created.
--
-- sessions.user_agent_sha256 holds fingerprint(user_agent), which SQL cannot turn back into a
-- family, so the label is computed at write time. Rows created before this migration stay null
-- and are served as `unknown`; nothing branches on the value.
--
-- sessions_user_live_idx is partial on `revoked_at is null`, so it cannot serve the newest-first
-- full scan the list orders by.

alter table lineage.sessions add column user_agent_family text;
create index sessions_created_idx on lineage.sessions (created_at desc, session_id desc);
comment on column lineage.sessions.user_agent_family is
    'Coarse client label for the session list.';
