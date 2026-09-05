# Runbook — the merge gate, the nightly control, and `make test`

## The probes no workflow can run

CI runs on GitHub-hosted runners. They have no route to the deployed instance, no owner key,
and no host filesystem, so **no workflow — the merge gate or a scheduled one — asserts
anything about a running deployment**. A green run is a statement about the tree.

The two deployed-instance probes say so in their own first lines. `infra/verify.sh` dials the
API through `/run/glasswell/api.sock`, reads `/etc/glasswell/app.env` for the owner key, and
compares `/etc/systemd/system/glasswell-*` against `infra/systemd/`; `scripts/smoke.sh` reads
the same key file and asserts the served surface against the committed OpenAPI snapshot. A
runner has none of those three things, and a runner that did would be holding the production
credential.

So the probes are owned on the host:

| probe | asserts | run by |
|---|---|---|
| `infra/verify.sh` | services, unit files byte-identical to the tree, auth matrix, tile allowlist, network exposure, secrets, backup and restore-drill freshness | `scripts/deploy.sh` step 8, on every deploy |
| `scripts/smoke.sh` | the served surface: SMOKE.md's assertions, per-point lineage, the hostile layer ids, the committed contract against the served one | `scripts/deploy.sh` step 9, on every deploy |

Both are read-only and runnable at any time on the host, which is what a scheduled control
would use. Nothing runs them on a timer today: `infra/systemd/` carries the ingest, status,
scheduler, backup, restore-drill, lineage-retention, C-115B and Cloudflare-range timers, and
no verify unit. The
recurring assertion is therefore per deploy, not per day, and a deployment that drifts between
deploys is not observed until the next one.

**What this means when a gate is green.** "CI complete" is green means the tree passed the
suite. It does not mean the deployment is serving, that its units match the tree, or that the
snapshot on the host is the snapshot in the repository. `verify.sh` and `smoke.sh` are the
only evidence for those, and their exit codes are printed at the end of every `deploy.sh` run.
