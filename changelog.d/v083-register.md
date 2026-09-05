- [Fix] The web glossary-seed helper resolves `glossary_seed.yml` from its own module rather
      than from the process CWD, so the card vocabulary gate and the R9 coverage gate read
      the committed seed from any working directory instead of only from `web/`
- [Fix] The changelog page is written inside the outDir the build resolved, not always into
      `web/dist`: a build into another directory no longer writes over the tree being
      served, and gets the page its own rail links to. A build that resolved no outDir
      refuses rather than guessing one
- [Fix] Caddy redacts every credential-shaped query parameter in both listeners' access
      logs, not the four names the API happens to refuse: one `request>uri regexp` covers
      key, password, secret, token, session, csrf and auth in any identifier, so `?api_key=`
      no longer takes its 422 and leaves the key in the log
- [New] The Caddy log filter is gated on completeness rather than on a name list: the shipped
      pattern is compiled and exercised against every credential-shaped name, against the
      served parameters it must leave readable, and against everything the API's own
      access-log filter redacts; a field declared twice in one `fields` block is refused,
      because Caddy keeps the last one silently
- [Fix] Four sessions migrating four databases on one cluster no longer collide on its
      roles: a migration that loses a cluster-global race is retried inside the runner,
      which is one transaction, so the second attempt takes the branch the winner
      committed. The first sharded CI run errored 843 tests on `pg_authid_rolname_index`
- [New] docs/ci-gate.md states which assertions no workflow can make: a GitHub runner has no
      route to the deployed instance, no owner key and no host filesystem, so `verify.sh` and
      `smoke.sh` own every deployed-instance probe, run per deploy rather than per day
- [New] Every `(source_id, stage)` the conformance registry declares a policy rule at has its
      own case: the declaration is still there, it has no executor, and dropping it leaves a
      load of implemented kinds. The parametrisation is derived from the seed and pinned to
      the registry, so a declaration at a new pair is covered without an edit
