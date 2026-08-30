- [Fix] Makefile: resolve the Python interpreter to the main checkout's virtualenv when the
      current tree has none, so `make lint` works in a git worktree; every dispatched track
      hit the failure and reached for a system ruff instead
- [Fix] test_d1_entry_gate.py: skip the wave-1 status-artifact gate in a linked worktree.
      Its guard keyed on work-output/ existing, so any dispatched track writing a status
      file there turned a self-disabling gate red with a message naming the wrong cause
