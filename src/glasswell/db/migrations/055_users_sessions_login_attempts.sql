-- Owner-created accounts and their server-side sessions. No registration path exists.

create table lineage.users (
    user_id             text primary key,
    username            text not null,
    password_hash       text not null check (password_hash like '$argon2id$%'),
    role                text not null check (role in ('owner', 'viewer')),
    created_at          timestamptz not null,
    created_by          text not null,
    password_changed_at timestamptz not null,
    last_login_at       timestamptz,
    disabled_at         timestamptz,
    disabled_by         text,
    check (disabled_at is null or disabled_by is not null),
    check (username = lower(username) and length(username) between 3 and 64)
);
create unique index users_username_idx on lineage.users (username);

create table lineage.sessions (
    session_id          text primary key,
    sha256              text not null unique check (sha256 ~ '^[0-9a-f]{64}$'),
    user_id             text not null references lineage.users (user_id),
    created_at          timestamptz not null,
    last_seen_at        timestamptz not null,
    idle_expires_at     timestamptz not null,
    absolute_expires_at timestamptz not null,
    revoked_at          timestamptz,
    revoked_reason      text check (revoked_reason in
                            ('logout', 'rotated', 'password_changed', 'admin', 'swept')),
    created_ip          text not null,
    user_agent_sha256   text,
    check (absolute_expires_at > created_at),
    check (revoked_at is null or revoked_reason is not null)
);
create index sessions_user_live_idx on lineage.sessions (user_id) where revoked_at is null;
create index sessions_expiry_idx on lineage.sessions (absolute_expires_at);

create table lineage.login_attempts (
    attempt_id         text primary key,
    attempted_at       timestamptz not null,
    username_submitted text not null check (username_submitted = lower(username_submitted)),
    client_ip          text not null,
    outcome            text not null check (outcome in
                           ('success', 'bad_credential', 'locked', 'rate_limited', 'disabled')),
    session_id         text
);
create index login_attempts_username_idx
    on lineage.login_attempts (username_submitted, attempted_at desc);
create index login_attempts_ip_idx on lineage.login_attempts (client_ip, attempted_at desc);
-- The known-good-IP bypass reads this and nothing else, so it is its own index.
create index login_attempts_known_good_idx
    on lineage.login_attempts (username_submitted, client_ip)
    where outcome = 'success';

comment on table lineage.users is
    'Owner-created accounts. No self-registration and no password reset by email.';
comment on column lineage.login_attempts.username_submitted is
    'The submitted string, not a resolved user: counting unknown names closes the lock oracle.';
comment on column lineage.sessions.absolute_expires_at is
    'Never extended. Idle refresh moves idle_expires_at only.';
comment on column lineage.sessions.sha256 is
    'The only representation at rest. Cleartext is returned once in a cookie and never stored.';

grant select, insert, update on lineage.users to glasswell_api;
grant select, insert, update, delete on lineage.sessions to glasswell_api;
grant select, insert, delete on lineage.login_attempts to glasswell_api;
-- Users are soft-disabled, never deleted: a disabled row is what a session FK still points at.
revoke delete, truncate on lineage.users from glasswell_api;
revoke truncate on lineage.sessions, lineage.login_attempts from glasswell_api;
