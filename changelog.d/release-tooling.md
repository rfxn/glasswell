- [New] `make release` turns a two-digit odometer one notch and tags it: `0.20`, `0.21`, …
      `0.99`, then `1.0`, `1.01`, … `1.99`, `2.0`. There is no minor and no patch level, so
      the target takes no argument — a fix and a redesign are both one notch, because the
      changelog and not the number is where a reader finds out which it was. `MAJOR=1` jumps
      a major for a `/v2` contract event (blueprint §3.6.1) and is the only exception
- [New] `VERSION` carries the owner literal and pyproject carries the PEP 440 equivalent,
      because a release segment with a leading zero is not canonical and packaging collapses
      `1.01` to `1.1` whether or not the file says so. The mapping is injective and
      order-preserving, so the two spellings can never name different releases; the tag, the
      `## v<version>` heading, its `<a id="v...">` anchor and the header stamp are one string.
      `tests/unit/test_release_tooling.py` walks 0.99→1.0→1.01, holds `1.01` apart from
      `1.10`, and holds the pattern's four copies — Python, the page, the stamp, the vite
      define — to the same verdict on the same eighteen strings
- [New] The release refuses, naming every reason at once: a dirty tree, a topic branch, a
      `HEAD` the remote has not seen, an existing tag, nothing pending in `changelog.d`, or a
      fold the page would not render. It then folds the pending fragments and every dated
      section still under `## Unreleased` into one version section, and puts those same
      entries in the commit body and in an annotated tag. `DRY=1` prints all of it — preflight
      verdict included — and writes nothing; `make release-check` prints the same verdict and
      exits non-zero, which is what lets `make ship` stop before it builds
- [New] Nothing can tag a changelog that will not render. Every line of every fragment goes
      through the page's own parser and renderer, and the whole candidate `CHANGELOG.md` goes
      through them again, before `VERSION`, the file, the commit or the tag is touched — and
      CI runs the same check on every pull request, so a bad fragment fails at merge rather
      than at release. `make ship` orders it check → build → release → rebuild → deploy, so a
      build failure cannot strand a fresh tag and a deploy cannot carry a bundle older than
      the release it is named for
- [New] `/changelog/`: the changelog rendered to a static page in the app's own shell, with
      the palette, type ramp and font faces lifted out of `web/src/style.css` at render time
      rather than copied, and the theme read from the same `glasswell.theme` key the rail
      writes. `npm run build` renders it through a vite plugin, so CI's web job and the deploy
      runbook's frontend rebuild both produce it; behind a Make target both would have shipped
      a header stamp pointing at a 404
- [New] The page's parser is the house grammar and nothing else — four tags, indented
      continuations, anchored version headings, dated subsections, paragraphs — and it
      **refuses** a bullet in another flavour, a table, a fence, an unknown tag or an anchor
      that names a different version, naming the file and the line. One implementation, three
      callers: the fragment check, the release gate and the page itself. A changelog with a
      mistake in it stops the release instead of rendering the mistake as prose
- [Change] The rail's build stamp is a link: `v0.20+3b83fcb` pointing at
         `/changelog/#v0.20`, same-origin, still one writer, still inside the fixed read
         column. The `build` eyebrow goes when a version is present — the value names itself
         and the column is 132 px at 1024 — and stays on an unreleased build, which links to
         the page without a fragment because `#v0.0-dev` is an anchor that does not exist
- [New] `make deploy` scripts the runbook rather than describing it: `git archive HEAD` over
      ssh, `tests/` tarred separately because `.gitattributes` export-ignores it and
      `smoke.sh` reads its snapshot on the host, `web/dist` to the web root, dependencies
      only when `requirements.lock` moved, then `install.sh`, `glasswell-api` and `martin`
      restarted, `verify.sh` and `smoke.sh`. It refuses a dirty tree, an untagged `HEAD`
      unless `GW_DEPLOY_ALLOW_UNTAGGED=1`, and a `web/dist` older than `VERSION` or
      `CHANGELOG.md` — a stale bundle ships the previous release's page under this one's tag
- [New] `verify.sh` asserts the changelog page is on the host and answers 200. There is no
      SPA fallback (DR-57), so `/changelog/` resolves only because it is a real directory
      behind the existing `StaticFiles(html=True)` mount — no API and no Caddy change
- [Fix] The fold moves what was pending and rewrites nothing: `difflib` reports it as a pure
      insertion, and the moved region is asserted byte-identical and contiguous — 1,388 lines
      at the same sha256. The previous version's anchor stays with its own heading rather than
      being dragged into the new section, which a twice-folded document now proves
- [Fix] `changelog-assemble.py` accepts `[Remove]`, which `CHANGELOG.md` has used five times
      and the fragment check would have rejected on the first line of a fragment that used it
- [Fix] `release.py` refuses a `--set` outside the grammar and a `VERSION` file left at the
      pre-scheme `0.1.0` in prose rather than with a traceback, and names a modified file by
      its whole name — git's porcelain opens every line with two status columns, and stripping
      them off by eye turned `Makefile` into `akefile`
