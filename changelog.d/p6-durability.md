- [New] verify.sh reads the restore-drill receipt instead of only its timer: the receipt's
      schema head must equal the live head, and the receipt must be recent, so a drill that
      passed against a stale dump and a receipt that stopped updating both fail
- [New] Offsite push receipt at /var/lib/glasswell-backup/offsite.json — generation, dump
      identity, per-stream files and bytes from rsync --stats — plus an offsite_copy status
      job and verify.sh assertions over it; recorded from the sending side only, because the
      forge grant is rrsync -wo and this host cannot read the far side back
- [New] Replacement-host recovery drill, runbook, receipt shape, recovery_drill status job
      and stub-based unit tests; globals then dump then raw zone, refusing the production
      database. It has never been executed end to end and every surface says so
- [New] verify.sh asserts systemd units in the reverse direction: every glasswell-* unit on
      the host must be declared in infra/systemd, which the tree-walking loop could never see
- [New] glasswell-durable-write.py, the shared atomic receipt writer with the target-safety
      checks the restore drill established
- [Change] remote_backup_copy disclosure moves from not_instrumented to limited and states
           the write-only read-back limit; a replacement_host_recovery disclosure states that
           the recovery path is mechanised and unexercised
- [Change] infra/README.md gains a durability-proofs section recording what each receipt does
           not prove, and the removal procedure for the undeclared glasswell-repromote units
