# Releasing glasswell

One release per merge train, cut from `main`, tagged, and readable at `/changelog/` on the
deployed instance. The header stamp in the rail is the link: it reads `v0.20+3b83fcb` and
points at that version's own heading.

```bash
make changelog-lint       # every fragment and CHANGELOG.md against the page grammar
make release-check        # every precondition and the render gate; exits 1 if blocked
make release DRY=1        # the same verdict plus the whole fold, printed; always exits 0
make release              # bump, fold, commit, annotate the tag
make build-web            # dist/, changelog page included
make deploy               # tar over ssh to $GW_DEPLOY_HOST, then verify.sh and smoke.sh
make ship                 # check, build, release, rebuild, deploy — first failure stops it
```

## 1. The version is an odometer, not semver

`MAJOR.NN`. Every release turns it one notch. `NN` runs `0` through `99` and then rolls into
the next major.

```
0.20 → 0.21 → 0.22 → … → 0.99 → 1.0 → 1.01 → 1.02 → … → 1.10 → … → 1.99 → 2.0
```

There is no minor level and no patch level, so `make release` takes no argument. A fix, a new
endpoint and a redesign are all one notch, because the changelog — not the number — is where a
reader finds out which it was. The number's job is to be orderable and quotable.

Read `X.0` as "the zeroth of X" and `X.01` as "the first". The single digit only ever appears
at `.0`; every other reading is two digits, which is why `1.01` and `1.10` are eight releases
apart rather than one.

## 2. Where the version lives

| File | Holds | Why |
|---|---|---|
| `VERSION` | the owner literal, `1.01` | source of truth; `scripts/release.py` writes it |
| `pyproject.toml` | the PEP 440 equivalent, `1.1` | a release segment with a leading zero is not canonical, and packaging collapses `1.01` to `1.1` whether or not the file says so |
| tag, `## v1.01 — <date>`, `<a id="v1.01">`, header stamp | the owner literal | one string, four surfaces |

The two forms never disagree about *which* release they name: owner `M.NN` maps to PEP 440
`M.NN` as integers, which is injective and order-preserving — `1.1 < 1.2 < … < 1.10 < 1.99 <
2.0` in packaging's ordering is exactly odometer order. What differs is only the spelling of
the zero-padded segment, and the padded spelling is the one every reader-facing surface uses.
`tests/unit/test_release_tooling.py` pins the boundaries:

- `test_the_odometer_rolls_from_99_into_the_next_major`
- `test_the_release_after_a_major_is_x01_not_x1`
- `test_v101_and_v110_are_nine_notches_apart_and_pep440_agrees`
- `test_pyproject_stores_the_pep440_spelling_of_the_owner_literal`
- `test_the_tag_the_heading_and_the_stamp_are_one_string`
- `TestTheOdometerGrammarIsNotFourOpinions` — the pattern is written out in `release.py`,
  `render-changelog.py`, `stamp.ts` and `vite.config.ts`; this reads all four and holds them
  to the same verdict on the same eighteen strings, so a grammar change cannot land in three

## 3. What `make release` does, and what stops it

It **refuses**, naming every reason at once, unless:

- the working tree is clean — a release describes a commit, and an uncommitted file is in none;
- the branch is `main`;
- `HEAD` is level with `origin/main`, so the tag names a commit the remote has seen;
- at least one fragment is pending in `changelog.d/` — a tag whose body is empty is the thing
  this scheme exists to prevent;
- the target tag does not already exist;
- **every line of every fragment parses**, and **the whole candidate `CHANGELOG.md` renders**.

The last one is the seam that matters. `read_entries` used to check only a fragment's first
line, so `- [Bogus] …` on line 2 reached a cut tag and was refused afterwards by the build.
Now the fragment goes through the page's own parser and renderer, the assembled document goes
through them again, and both happen before anything is written. One implementation
(`render-changelog.py`), three callers, so the fold and the page cannot drift apart.

Then it bumps `VERSION` and `pyproject.toml`, opens
`<a id="v<version>"></a>` + `## v<version> — <ISO date>` beneath `## Unreleased`, moves every
pending fragment's entries and every dated `### ` section still sitting under `## Unreleased`
into it, deletes the fragments, commits `Release v<version>` with the entries in the body, and
creates an **annotated** tag whose message is those same entries.

`DRY=1` runs the preflight, prints the fold, the commit and the tag body, and writes nothing —
including on a branch that would be refused, because inspecting the next release is not
releasing it. It therefore always exits 0 and cannot gate anything; `make release-check` is the
same preflight with an exit code, and is what `make ship` runs first.

`make ship` is ordered **check → build → release → rebuild → deploy**. Building before the tag
means a build failure cannot strand a fresh tag; rebuilding after it means the stamp and the
changelog page carry the version that was just cut, and `deploy.sh` refuses a `web/dist` older
than `VERSION` or `CHANGELOG.md` in case anyone skips that step.

## 4. `MAJOR=1` — the exception, not a level

`make release MAJOR=1` jumps to `(X+1).0` without walking the rest of the odometer. It is for
a **contract event**: blueprint §3.6.1's `/v2`, where the served API surface changes in a way
`/v1`'s freeze does not permit. Nothing else justifies it. A large feature is still one notch.

`make release SET=1.05` names a version outright and exists for repair, not for routine use;
it still refuses to go backwards.

## 5. The changelog page

`scripts/render-changelog.py` renders `CHANGELOG.md` to `dist/changelog/index.html` with the
app's own palette and faces, lifted out of `web/src/style.css` at render time so the two cannot
drift. `npm run build` runs it through a vite plugin rather than a Make step, so CI's web job
and the deploy runbook's "rebuild the frontend" both produce it — behind a Make target, both
would ship a header stamp linking to a 404.

The parser accepts exactly the house grammar and **refuses everything else, naming the line**:
`[New]` `[Change]` `[Fix]` `[Remove]` entries with indented continuations, `## Unreleased`,
anchored `## v<version> — <date>`, dated `### ` subsections, and plain paragraphs. A bullet in
another flavour, a table, a code fence or an unknown tag stops the release. That is deliberate:
the alternative is a page that renders a mistake as though it were prose.

The same parser is the fragment check (`make changelog-lint`, and the `collateral` CI job on
every pull request) and the release's render gate, so a fragment that would not render fails at
merge, and if it somehow reaches `main` it fails before the tag rather than after it.

`/changelog/` resolves through the existing `StaticFiles(html=True)` mount at `/` — a real
directory with a real `index.html`, because there is no SPA fallback (DR-57). `infra/verify.sh`
asserts both the file and the `200`.

## 6. `make deploy`

`scripts/deploy.sh` is infra/README.md's runbook steps 1, 2 and 4, scripted. It **refuses** a
dirty tree, and it refuses an untagged `HEAD` unless `GW_DEPLOY_ALLOW_UNTAGGED=1` — rolling
releases deploy tags, and an untagged deploy is a host nobody can name the contents of.

It tars `git archive HEAD` over ssh, then tars `tests/` from the working tree separately
because `.gitattributes` export-ignores it and `scripts/smoke.sh` reads
`tests/contract/openapi_snapshot.json` on the host. Never `rsync --delete`: it stalls on this
path. `web/dist` goes to `/opt/glasswell/web`, dependencies are reinstalled only when
`requirements.lock` changed, `infra/install.sh` runs, `glasswell-api` restarts, and
`verify.sh` and `smoke.sh` report. Both `glasswell-api` and `martin` are restarted, as runbook
step 4 has it — `install.sh` can have just placed `infra/martin/config.yaml`, and without the
restart the new config is inert and `verify.sh`'s catalogue check fails the deploy two steps
later. Migrations are opt-in (`--with-migrations`); the tile-function reinstall stays a hand
step because it is conditional on `src/glasswell/marts/tiles.py` having moved.

## 7. Cadence

A merge train is a release. Fold the train, cut the notch, deploy the tag. Six trains landing
in one day is one release with six dated sections under one heading, not six tags — the
version marks what the deployed host is running, and the dated sections inside it say what
each train did.
