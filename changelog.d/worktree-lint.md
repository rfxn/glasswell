- [Fix] Makefile: `make lint` and `make fmt` borrow the main checkout's interpreter when the
      current tree has none, so they work in a git worktree; every dispatched track hit the
      failure and reached for a system ruff instead. The test targets deliberately do not
      borrow it, because that venv installs glasswell editable against its own src
- [Fix] test_d1_entry_gate.py: skip the wave-1 status-artifact gate in a linked worktree.
      Its guard keyed on work-output/ existing, so any dispatched track writing a status
      file there turned a self-disabling gate red with a message naming the wrong cause
