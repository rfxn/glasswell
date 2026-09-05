- [New] `infra/bin/host-runner.sh`: a long host job runs as a chain of transient units with
      one `systemd-run --wait` inside the runner and none outside it, a log at
      `/var/log/glasswell/<job>.log` and a status document at
      `/var/lib/glasswell/runs/<job>.json` rewritten whole and atomically after every
      transition — the step, its unit, its exit, its `systemd_result`, its peak memory and
      its full summary line, plus a stamp per transition; `--status <job>` prints it, a
      failing step stops the chain and the status names it, and a job that already has a
      status file refuses to run again without `--force`
- [New] the step's summary reaches the status file whole: the first ad-hoc host runner cut
      it at 600 characters, which left the figures it reported unparseable, and nothing in
      the tracked runner cuts, heads or tails a machine-readable line
- [New] a step is judged by the evidence it wrote, not by its exit status: every glasswell
      ingest and mart entry point prints one JSON document when it commits, and a step that ends
      without it — or without the line `--expect` names — is treated as not done and stops the
      chain, whatever the exit says, with `steps[].judged_by` recording which reading answered.
      Measured 2026-09-05: `systemctl stop` of a running promotion answers `Result=success` and
      exit 0, and the ad-hoc runner ran the next step over a promotion that had not happened. A
      step the host ended rather than the step itself — `signal`, `core-dump`, `oom-kill`,
      `timeout`, `watchdog`, `start-limit-hit`, `resources`, `protocol` — stops the chain even
      under `--keep-going`, which is for a step that failed and said so
- [New] `--resume` continues a job whose status says `stopped` under the same job name, log
      and status file, numbering the new steps after the ones already recorded, and
      `--after-job` starts one job behind another by reading that job's status file rather
      than a unit's `Result`, which answers `success` for a unit that has been collected;
      the wait is bounded by `--after-timeout` (default 86400 s) and the deadline it is
      waiting to is in the `waiting` state, so a follower behind a job that never finishes
      stops and says so rather than waiting forever. `runbook-tx-load.md` Step 4 arms the
      marts behind the Step 3 promotion this way, replacing a hand-off the operator had to
      watch for; a promotion that stopped stops the marts too, because marts rebuilt over a
      promotion that did not happen would publish totals for rows that are not there
- [New] install.sh places the runner at `/usr/local/sbin/host-runner.sh` and creates
      `/var/lib/glasswell/runs` (root:glasswell 0750, so a step cannot rewrite the verdict on
      its own work) and `/var/log/glasswell`; verify.sh asserts both directories and holds the
      installed runner byte-identical to the tree
- [New] install.sh retires the five ad-hoc runners of 2026-09-05 as it places the tracked one,
      scripts and status files together, into `/var/lib/glasswell/runs/archive/` — never
      deleted, because a load's own record is the evidence that it happened. Without it the
      Colorado runbook's first tracked run refuses: `co-load` is the job name the runbook
      launches and the ad-hoc verdict already sat under it. Never a live one: a runner whose
      unit is active, or whose job reads `running` or `waiting`, keeps its script, status and
      stamps and is retired by the next deploy instead, because a deploy lands during a load
      and a poll path that disappears mid-run is worse than a retirement that waits
- [Change] every long host step an operator is told to run is a job on the runner, and no
         fenced block in any runbook — or in `infra/README.md` — starts a unit: the loads and
         promotions of `runbook-basin-load.md`, `runbook-mt-load.md`, `runbook-nm-promotion.md`,
         `runbook-nm-tier2.md`, `runbook-tx-load.md` and `runbook-scheduler.md`, Colorado's
         Steps 1-5 as one six-unit chain, the mart refresh `deploy.sh` documents, and
         `infra/README.md`'s step 4 tile-function reinstall, which was the last `--pipe --wait`
         — an operator reading output inline is an operator whose job dies with the session.
         Each is launched detached and followed by the command that polls its status file; the
         prose that discusses systemd still does
- [Change] Texas Step 3 sizes its promotion batches by expected rows rather than by a count
         of years: the 2011-2016 batch was OOM-killed at `MemoryMax=6G` on 2026-09-05 after
         batches of 5.23 M, 5.72 M and 6.72 M rows had landed under the same ceiling, so the
         budget is about 5 M rows per unit, the ceiling is not raised on an 11 GB host, and
         the status file's `systemd_result` is what separates a kill to resume from a data
         refusal to stop
- [New] `scripts/deploy.sh` records every remote step into `deploy-<tag>-<commit>.json` on
      the host and reads the verdict back out of it, so a ship whose workstation dies is
      still readable and an ssh that returned 0 is no longer the whole answer
