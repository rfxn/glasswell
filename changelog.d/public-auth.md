- [Change] blueprint: Cloudflare Access is not enabled on this account, so ingress is
           Cloudflare Tunnel only and authorization is the application's own session
           login; SB-06 §5 and SB-04 §3.1 amended, the ruled Access design retained as
           the design to reinstate
- [New] argon2-cffi pinned; Argon2id at t=3, m=64MiB, p=2, sized against the two-worker
      uvicorn RAM budget, with a floor assertion so the parameters cannot be lowered
