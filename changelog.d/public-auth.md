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
