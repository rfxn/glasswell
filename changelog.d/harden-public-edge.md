- [Fix] api: POST /v1/session/password charges the login bucket before it verifies the
      current password; the session router is included without enforce_rate_limit, so a
      held session cookie bought unlimited current-password guesses against an account it
      could not otherwise take over
- [Fix] verify.sh: resolve the public hostname at a public resolver and carry the address
      on the four edge probes; lab DNS is split-horizon and NXDOMAINs the record, so every
      probe answered 000 and the deploy gate read an unreachable name as a broken edge
- [New] verify.sh: assert the installed Caddyfile equals the tree, the front-door
      equivalent of the connector drift check; deploy never installs it, so the two
      diverged silently for ten days with only an inert stale origin to show for it
- [Fix] install.sh, deploy.sh: enable and start glasswell-cf-ranges.timer, which shipped
      installed but armed by nothing, so the weekly Cloudflare range refresh its own file
      header advertises had never run on any host
- [New] verify.sh: assert the range-refresh timer is enabled and active; the freshness
      check beside it cannot fail on a deploy, because install.sh rewrites the file
      minutes before verify reads its mtime
