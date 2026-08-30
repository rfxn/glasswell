- [Change] blueprint: Cloudflare Access is not enabled on this account, so ingress is
           Cloudflare Tunnel only and authorization is the application's own session
           login; SB-06 §5 and SB-04 §3.1 amended, the ruled Access design retained as
           the design to reinstate
- [New] argon2-cffi pinned; Argon2id at t=3, m=64MiB, p=2, sized against the two-worker
      uvicorn RAM budget, with a floor assertion so the parameters cannot be lowered
- [New] migration 056: lineage.users, lineage.sessions and lineage.login_attempts, with
      owner-only account creation, session tokens stored as sha256 alone, and a CHECK
      that refuses any password hash that is not Argon2id
- [New] login throttling: per-account and per-IP backoff on a doubling curve capped at 900s,
      15-minute time-boxed lockout, and a known-good-IP bypass so a flood from an
      unfamiliar address cannot lock the owner out of their own network
- [Fix] the client address is resolved from a Caddy-set edge marker, never from
      X-Forwarded-For; uvicorn runs with --forwarded-allow-ips '*', under which the
      leftmost X-Forwarded-For entry is attacker-controlled
- [New] infra/cloudflare: the edge range list, a weekly refresh unit that refuses to
      publish a shrunken list, and a misconfiguration detector that never grants trust
- [New] CSRF tokens bound to the session hash and HMAC-signed, so a token minted for one
      session cannot be replayed into another and a caller with no session cannot mint
      one; a missing signing key is a startup abort, never a disabled check
- [New] session login with two roles (owner, viewer) over lineage.users: __Host- cookie,
      server-side session records, rotation on login, sliding idle expiry under a
      never-extended absolute cap, and server-side logout invalidation
- [Fix] /docs and /openapi.json were served anonymously; both now require a principal,
      and the auth-matrix coverage test walks the router rather than the OpenAPI
      document so a reachable-but-undeclared route cannot recur
- [Change] the static owner key is refused on the tunnel listener, demoting it to a
           LAN and deploy-gate credential; issued api_keys rows are unaffected
- [Change] GLASSWELL_ALLOW_ANON resolves to the viewer role rather than owner scope, and
           the API refuses to start when it is set together with GLASSWELL_PUBLIC=1
- [New] owner-only account administration at /v1/users: create, list, change role, soft
      disable and reset a password, each an audit event; the last enabled owner cannot
      be disabled or demoted, guarded by a row lock rather than a handler-side count
- [New] the four ruled rate-limit buckets applied on the /v1 router set: 120/min
      interactive, 60 service, 600 tiles and 30 per resolved address for anonymous, with
      one uniform 429 and a Retry-After rounded to 30s so the bucket that fired is not
      named; global concurrency stays unmet and is recorded as such
- [New] HSTS over https only, at a year with includeSubDomains and no preload
- [Change] credential redaction widened to password, token, session and csrf query
           parameters and to any gws_ session token anywhere in a log record; the
           tunnel listener gains its own Caddy log block, since a site inherits none
- [New] retention sweeps expired sessions after their absolute cap plus seven days and
      login attempts after ninety, keyed on the cap so a live session is unreachable
- [New] infra: the cloudflared ingress publishes one hostname to the Caddy tunnel listener
      and answers 404 for everything else, so the tile server is not reachable through
      the edge; install.sh gains --with-cloudflared and generates GLASSWELL_CSRF_KEY
- [Fix] verify.sh asserted only tree-to-host unit equality, so a unit installed on the
      host and declared in no repo file was invisible; the reverse assertion closes it
