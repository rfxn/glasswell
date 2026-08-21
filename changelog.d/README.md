# changelog.d — per-branch changelog fragments

`CHANGELOG.md` is the most contended file in the repository — in the 200 commits before
this directory existed it was touched by 60 of them, and every parallel track carried a
standing "batch your entries into one final commit" rule to keep merge trains resolvable.
Fragments remove the contention instead of managing it: **a track never edits
`CHANGELOG.md`**; it writes one file here that no other track will ever touch.

## Protocol

- One fragment per branch: `<branch-or-track>-<slug>.md` (for example
  `d1-p5-lease-equivalents.md`). If entry order matters at the merge train, prefix with a
  two-digit ordinal (`10-`, `20-`); fragments are folded in filename order.
- A fragment contains **only** ready-to-merge entry lines in the house style — no heading,
  no prose, no blank lines between entries:

  ```
  - [New] one entry, soft-wrapped at ~80 chars at clean phrase boundaries;
        continuation indent 6 spaces for [New]/[Fix], 9 for [Change]
  - [Fix] the next entry stacks directly underneath
  ```

- At the merge train the integrator runs `make changelog TITLE="<cycle title>"`, which
  folds every fragment under `### <date> — <title>` inside `## Unreleased`, in filename
  order, and deletes the fragments. Commit the fold and the deletions together.
- `scripts/changelog-assemble.py --check` fails while fragments are pending — run it
  before cutting a release so nothing is stranded here.

Direct edits to `CHANGELOG.md` remain integrator-only. This directory is export-ignored;
fragments never appear in a release archive.
