- [Fix] Makefile: resolve the Python interpreter to the main checkout's virtualenv when the
      current tree has none, so `make lint` works in a git worktree; every dispatched track
      hit the failure and reached for a system ruff instead
