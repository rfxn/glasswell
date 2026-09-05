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
- [New] `--resume` continues a job whose status says `stopped` under the same job name, log
      and status file, numbering the new steps after the ones already recorded, and
      `--after-job` starts one job behind another by reading that job's status file rather
      than a unit's `Result`, which answers `success` for a unit that has been collected
- [New] install.sh places the runner at `/usr/local/sbin/host-runner.sh` and creates
      `/var/lib/glasswell/runs` (0750) and `/var/log/glasswell`; verify.sh asserts both
      directories and holds the installed runner byte-identical to the tree
- [Change] the nineteen `systemd-run` sites across the seven runbooks are jobs on the
         runner, each launched detached and followed by the command that polls its status
         file; Colorado's Steps 1-5 are one six-unit chain, and no fenced block in any
         runbook starts a unit any more
- [Change] Texas Step 3 sizes its promotion batches by expected rows rather than by a count
         of years: the 2011-2016 batch was OOM-killed at `MemoryMax=6G` on 2026-09-05 after
         batches of 5.23 M, 5.72 M and 6.72 M rows had landed under the same ceiling, so the
         budget is about 5 M rows per unit, the ceiling is not raised on an 11 GB host, and
         the status file's `systemd_result` is what separates a kill to resume from a data
         refusal to stop
- [New] `scripts/deploy.sh` records every remote step into `deploy-<tag>-<commit>.json` on
      the host and reads the verdict back out of it, so a ship whose workstation dies is
      still readable and an ssh that returned 0 is no longer the whole answer
