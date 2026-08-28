- [Fix] Preserve the restore drill's implicit root credential so its constrained `SETUID` and
      `SETGID` capabilities can enter the PostgreSQL identity under the existing sandbox
- [Fix] Index the physical-neighbour mart's reverse subject foreign key so replacement no longer
      scans 7.96 million directed edges for each subject deletion
