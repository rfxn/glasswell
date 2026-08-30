- [New] verify.sh reads the restore-drill receipt instead of only its timer: the receipt's
      schema head must equal the live head, and the receipt must be recent, so a drill that
      passed against a stale dump and a receipt that stopped updating both fail. The head
      comparison waits for a drill that postdates the newest migration, because the drill is
      weekly and a migration deploy would otherwise red the verifier until Sunday
- [New] Offsite push receipt at /var/lib/glasswell-backup/offsite.json — generation, dump
      identity, per-stream files and bytes from rsync --stats — plus an offsite_copy status
      job and verify.sh assertions over it; recorded from the sending side only, because the
      forge grant is rrsync -wo and this host cannot read the far side back
- [New] Replacement-host recovery drill, runbook, receipt shape, recovery_drill status job
      and stub-based unit tests; globals then dump then raw zone. It refuses the production
      database by case-folded comparison and a plain-identifier allowlist, and refuses the
      production host itself when the live database is present or the API is serving, with
      the probe failing closed. It has never been executed end to end and every surface
      says so
- [New] verify.sh asserts systemd units in the reverse direction: every glasswell-* unit on
      the host must be declared in infra/systemd, which the tree-walking loop could never see
- [New] glasswell-durable-write.py, the shared atomic receipt writer with the target-safety
      checks the restore drill established
- [New] The verify.sh receipt helpers are executed under bash against real files by
      tests/unit/test_verify_helpers.py, not only grepped for
- [Change] remote_backup_copy disclosure moves from not_instrumented to limited and states
         the write-only read-back limit; a replacement_host_recovery disclosure states that
         the recovery path is mechanised and unexercised
- [Change] infra/README.md gains a durability-proofs section recording what each receipt does
         not prove, the removal procedure for the undeclared glasswell-repromote units, and
         the new coupling that a receipt it cannot publish fails the nightly backup
- [Fix] The restore-drill job measures its dump's staleness at drill time rather than against
      now, so a healthy weekly drill no longer degrades every Tuesday and refuses every deploy
      until Sunday; a drill that genuinely restored an old dump still degrades
