- [Fix] restore drill: a scratch-cleanup failure no longer overwrites the cause that came
      first, so result.json still names the unrestorable dump while scratch_removed carries
      the cleanup miss
- [Fix] backup retention: a generation now expires as a unit on its dump's mtime, manifest
      first, so a generation straddling the cutoff can no longer strand a manifest without
      its archive and abort the next restore drill with manifest_dump_missing
- [Fix] backup retention: a prune that cannot delete now fails the run after the offsite
      push instead of logging a WARN and exiting 0, so OnFailure fires before the disk fills
- [Fix] verify.sh: the retention-sweep and status-collector result assertions now check run
      evidence; systemctl show -p Result answers success for a unit that is absent or has
      never run
