-- Bound request-created provenance without creating one counter row per request or time window.

create table lineage.api_rate_windows (
    principal_id       text not null check (length(principal_id) between 1 and 128),
    operation          text not null check (length(operation) between 1 and 128),
    window_started_at  timestamptz not null,
    requests           integer not null check (requests > 0),
    primary key (principal_id, operation)
);

comment on table lineage.api_rate_windows is
    'One mutable fixed-window counter per principal and provenance-writing API operation.';

grant select, insert, update on lineage.api_rate_windows to glasswell_api;
revoke delete, truncate on lineage.api_rate_windows from glasswell_api;
