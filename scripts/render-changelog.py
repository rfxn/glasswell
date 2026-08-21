#!/usr/bin/env python3
"""Render CHANGELOG.md to the static page the header stamp links to.

    scripts/render-changelog.py --out web/dist/changelog   # index.html + css + js
    scripts/render-changelog.py --check                    # parse only, write nothing

The changelog is written in one strict house grammar — tagged entry lines, six/nine/eleven
space continuations, `## v<version> — <date>` headings behind an explicit anchor, dated
`### ` train subsections and plain paragraphs. That grammar is small enough to parse here,
so the page carries no markdown dependency and, more usefully, a line outside the grammar
stops the build naming the line rather than rendering as something the author did not mean.

Palette, type ramp and font faces are lifted out of `web/src/style.css` at render time: the
page is the app's own tokens, not a second copy of them that drifts.
"""

from __future__ import annotations

import argparse
import html
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STYLE = ROOT / "web" / "src" / "style.css"

# The four tags the changelog actually uses. `scripts/changelog-assemble.py` admits the same
# set for fragments; tests/unit/test_release_tooling.py holds the two lists to each other.
TAGS = ("New", "Change", "Fix", "Remove")

TITLE = "# Changelog"
UNRELEASED = "## Unreleased"
VERSION_HEADING = re.compile(
    r"^## (v(?:0|[1-9][0-9]*)\.(?:0|0[1-9]|[1-9][0-9])) — (\d{4}-\d{2}-\d{2})$"
)
TRAIN_HEADING = re.compile(r"^### (\d{4}-\d{2}-\d{2}) — (\S.*)$")
ANCHOR = re.compile(r'^<a id="(v[0-9.]+)"></a>$')
ENTRY = re.compile(r"^- \[([A-Za-z]+)\] (\S.*)$")
# A line the grammar has no room for: another list flavour, a fence, a table, raw HTML.
REFUSED_START = re.compile(r"^(?:[-+>|]|\*(?!\*)|```|~~~|<|\d+[.)]\s)")
LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
BOLD = re.compile(r"\*\*(.+?)\*\*")

COPYRIGHT = "Copyright (C) 2026 Ryan MacDonald · All rights reserved"
STRAP = "no naked numbers · every figure traces to a checksummed regulator file"

_ORPHAN_ANCHOR = "anchor not followed by a version heading"
# A fragment is a release section's body with the headings taken away, so the smallest
# document that can hold one is this. `check_fragment` parses that and subtracts the offset.
FRAGMENT_PREAMBLE = (TITLE, "", UNRELEASED, "")


class Refused(SystemExit):
    def __init__(self, source: Path, line: int, text: str, why: str) -> None:
        super().__init__(f"{source}:{line}: {why}\n  {line:>5} | {text}")


@dataclass
class Entry:
    tag: str
    text: str
    line: int


@dataclass
class Para:
    text: str
    line: int


@dataclass
class Train:
    date: str
    title: str
    slug: str
    line: int
    blocks: list[Entry | Para] = field(default_factory=list)


@dataclass
class Release:
    label: str
    anchor: str
    date: str
    blocks: list[Entry | Para] = field(default_factory=list)
    trains: list[Train] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not self.blocks and not self.trains


@dataclass
class Changelog:
    intro: list[Para] = field(default_factory=list)
    releases: list[Release] = field(default_factory=list)


def slugify(text: str) -> str:
    return re.sub(r"-{2,}", "-", re.sub(r"[^a-z0-9]+", "-", text.lower())).strip("-")


def parse(source: Path) -> Changelog:
    return parse_text(source.read_text(), source)


def parse_text(text: str, source: Path, offset: int = 0) -> Changelog:
    """Every line is classified or the render stops. Silence is not a rendering strategy.

    `offset` shifts the reported line numbers, so a fragment checked inside a synthetic
    document still refuses at its own line (see `check_fragment`).
    """
    lines = text.splitlines()
    doc = Changelog()
    release: Release | None = None
    train: Train | None = None
    open_entry: Entry | None = None
    open_para: Para | None = None
    pending_anchor: tuple[int, str, str] | None = None
    slugs: set[str] = set()
    seen_title = False

    def target() -> list[Entry | Para]:
        if train is not None:
            return train.blocks
        if release is not None:
            return release.blocks
        return doc.intro  # type: ignore[return-value]

    for index, line in enumerate(lines, 1):
        number = index + offset
        if not line.strip():
            open_entry = open_para = None
            continue

        if line.startswith(" "):
            if open_entry is not None:
                open_entry.text += " " + line.strip()
            elif open_para is not None:
                open_para.text += " " + line.strip()
            else:
                raise Refused(source, number, line, "indented line with no entry above it")
            continue

        open_entry = None

        if pending_anchor and not line.startswith("## "):
            raise Refused(source, pending_anchor[0], pending_anchor[2], _ORPHAN_ANCHOR)

        if line == TITLE:
            open_para = None
            if seen_title:
                raise Refused(source, number, line, "a second document title")
            seen_title = True
            continue

        if line.startswith("#"):
            open_para = None
            if not seen_title:
                raise Refused(source, number, line, f"a heading before {TITLE!r}")
            release, train, pending_anchor = _heading(
                source, number, line, doc, release, pending_anchor, slugs
            )
            continue

        anchor = ANCHOR.match(line)
        if anchor:
            open_para = None
            if pending_anchor:
                raise Refused(source, number, line, "two anchors with no heading between them")
            pending_anchor = (number, anchor.group(1), line)
            continue

        entry = ENTRY.match(line)
        if entry:
            open_para = None
            if entry.group(1) not in TAGS:
                raise Refused(
                    source,
                    number,
                    line,
                    f"unknown entry tag [{entry.group(1)}] — the grammar is "
                    + ", ".join(f"[{tag}]" for tag in TAGS),
                )
            if release is None:
                raise Refused(source, number, line, "an entry above the first heading")
            open_entry = Entry(entry.group(1), entry.group(2), number)
            target().append(open_entry)
            continue

        if REFUSED_START.match(line):
            raise Refused(source, number, line, "not the changelog grammar")

        # Soft-wrapped prose is one paragraph until a blank line, exactly as it reads in the
        # source: a line break in markdown is not a paragraph break and must not become one.
        if open_para is not None:
            open_para.text += " " + line
        else:
            open_para = Para(line, number)
            target().append(open_para)

    if pending_anchor:
        raise Refused(source, pending_anchor[0], pending_anchor[2], _ORPHAN_ANCHOR)
    if not seen_title:
        raise Refused(source, 1, lines[0] if lines else "", f"first line must be {TITLE!r}")
    return doc


def check_fragment(path: Path) -> str:
    """Every line of one changelog.d fragment, through the page's own parser and renderer.

    Not a second validator: the fragment is wrapped in the smallest document that can hold it
    and run through `parse_text` and `render_html` themselves, so what the fold admits and what
    the page later accepts cannot diverge. gate-rel B1 — a `[Bogus]` tag on line 2 of a
    fragment used to survive `read_entries`' first-line check all the way to a cut tag.
    """
    text = path.read_text().strip("\n")
    if not text.strip():
        raise Refused(path, 1, "", "an empty fragment")
    document = "\n".join([*FRAGMENT_PREAMBLE, text]) + "\n"
    doc = parse_text(document, path, offset=-len(FRAGMENT_PREAMBLE))
    # The renderer is where the inline grammar is judged, so an unbalanced code span in a
    # fragment refuses here rather than in the build that follows the tag.
    render_html(doc, path)
    blocks = [
        block
        for release in doc.releases
        for holder in (release.blocks, *(train.blocks for train in release.trains))
        for block in holder
    ]
    if not any(isinstance(block, Entry) for block in blocks):
        raise Refused(path, 1, text.splitlines()[0], "no changelog entry in this fragment")
    return text


def _heading(source, number, line, doc, release, pending_anchor, slugs):
    """One heading: `## Unreleased`, `## v<version> — <date>`, or a dated `### ` train."""
    if line == UNRELEASED:
        if pending_anchor:
            raise Refused(
                source,
                pending_anchor[0],
                pending_anchor[2],
                "the Unreleased heading carries no anchor",
            )
        release = Release("Unreleased", "unreleased", "")
        doc.releases.append(release)
        return release, None, None

    version = VERSION_HEADING.match(line)
    if version:
        tag, when = version.group(1), version.group(2)
        if pending_anchor is None:
            raise Refused(source, number, line, f'no <a id="{tag}"></a> above this heading')
        if pending_anchor[1] != tag:
            raise Refused(
                source, number, line, f"anchor id {pending_anchor[1]!r} does not name {tag!r}"
            )
        release = Release(tag, tag, when)
        doc.releases.append(release)
        return release, None, None

    train = TRAIN_HEADING.match(line)
    if train:
        if release is None:
            raise Refused(source, number, line, "a dated section outside any release")
        slug = slugify(f"{train.group(1)} {train.group(2)}")
        while slug in slugs:
            slug += "-x"
        slugs.add(slug)
        node = Train(train.group(1), train.group(2), slug, number)
        release.trains.append(node)
        return release, node, None

    if line.startswith("## "):
        raise Refused(source, number, line, "not `## Unreleased` and not `## v<version> — <date>`")
    if line.startswith("### "):
        raise Refused(source, number, line, "not `### <YYYY-MM-DD> — <title>`")
    raise Refused(source, number, line, "heading deeper than `### ` is outside the grammar")


def inline(text: str, source: Path, number: int) -> str:
    parts = text.split("`")
    if len(parts) % 2 == 0:
        raise Refused(source, number, text, "unbalanced ` — a code span opens and never closes")
    rendered = []
    for index, part in enumerate(parts):
        if index % 2:
            rendered.append(f"<code>{html.escape(part, quote=False)}</code>")
        else:
            rendered.append(_markup(html.escape(part, quote=False)))
    return "".join(rendered)


def _markup(escaped: str) -> str:
    def link(match: re.Match[str]) -> str:
        label, href = match.group(1), match.group(2)
        if href.startswith(("http://", "https://")):
            return f'<a href="{html.escape(href)}" rel="noreferrer">{label}</a>'
        # A repository-relative path is not served from /changelog/; naming it is honest,
        # linking it is a 404 that reads as a broken page rather than a missing file.
        return f'<span class="gw-cl-ref">{label}</span>'

    return LINK.sub(link, BOLD.sub(r"<strong>\1</strong>", escaped))


def tokens(style: Path) -> str:
    """The app's own faces and custom properties, lifted verbatim so they cannot diverge."""
    css = style.read_text()
    blocks = re.findall(r"@font-face\s*\{[^}]*\}", css)
    for selector in (r":root\s*\{[^}]*\}", r':root\[data-theme="light"\]\s*\{[^}]*\}'):
        match = re.search(selector, css)
        if match is None:
            raise SystemExit(f"{style}: no `{selector}` block to lift the palette from")
        blocks.append(match.group(0))
    return "\n\n".join(blocks)


def render_css(style: Path) -> str:
    return tokens(style) + PAGE_CSS


def render_html(doc: Changelog, source: Path) -> str:
    body = [
        '<a class="gw-skip" href="#gw-releases">Skip to the releases</a>',
        '<header class="gw-cl-head">',
        '  <a class="gw-brand" href="/" aria-label="glasswell — back to the app">',
        '    <img class="gw-mark" src="/brand/logo-mark-small.svg" alt="" width="512"'
        ' height="512">',
        '    <span class="gw-wordmark">glass<span class="gw-wordmark-well">well</span></span>',
        "  </a>",
        f'  <p class="gw-strap">{html.escape(STRAP)}</p>',
        "</header>",
        '<main id="gw-releases" class="gw-cl-main">',
        "  <h1>Changelog</h1>",
        '  <div class="gw-cl-intro">',
    ]
    for para in doc.intro:
        body.append(f"    <p>{inline(para.text, source, para.line)}</p>")
    body.append("  </div>")

    shown = [release for release in doc.releases if not release.empty]
    body += [
        '  <nav class="gw-cl-nav" aria-labelledby="gw-cl-navtitle">',
        '    <h2 id="gw-cl-navtitle" class="gw-cl-navtitle">Releases</h2>',
        "    <ol>",
    ]
    for release in shown:
        date = f'<time datetime="{release.date}">{release.date}</time>' if release.date else ""
        body.append(
            f'      <li><a href="#{release.anchor}">'
            f'<span class="gw-cl-ver">{html.escape(release.label)}</span> {date}</a></li>'
        )
    body += ["    </ol>", "  </nav>", '  <div class="gw-cl-releases">']

    for release in shown:
        body += _release_html(release, source)
    body += [
        "  </div>",
        "</main>",
        '<footer class="gw-cl-foot">',
        f"  <p>{html.escape(COPYRIGHT)}</p>",
        "</footer>",
    ]
    return PAGE_HTML.format(body="\n".join(f"    {line}" for line in body))


def _release_html(release: Release, source: Path) -> list[str]:
    date = (
        f'<span class="gw-cl-date"><time datetime="{release.date}">{release.date}</time></span>'
        if release.date
        else ""
    )
    out = [
        f'    <section class="gw-cl-rel" aria-labelledby="{release.anchor}">',
        f'      <h2 id="{release.anchor}">'
        f'<span class="gw-cl-ver">{html.escape(release.label)}</span> {date}</h2>',
    ]
    out += _blocks_html(release.blocks, source, indent=6)
    for train in release.trains:
        out += [
            f'      <section class="gw-cl-train" aria-labelledby="{train.slug}">',
            f'        <h3 id="{train.slug}"><span class="gw-cl-date">'
            f'<time datetime="{train.date}">{train.date}</time></span> '
            f"{inline(train.title, source, train.line)}</h3>",
        ]
        out += _blocks_html(train.blocks, source, indent=8)
        out.append("      </section>")
    out.append("    </section>")
    return out


def _blocks_html(blocks: list[Entry | Para], source: Path, indent: int) -> list[str]:
    pad = " " * indent
    out: list[str] = []
    run: list[Entry] = []

    def flush() -> None:
        if not run:
            return
        out.append(f'{pad}<ul class="gw-cl-entries">')
        for entry in run:
            out.append(
                f'{pad}  <li class="gw-cl-entry" data-tag="{entry.tag}">'
                f'<span class="gw-cl-tag">{entry.tag}</span>'
                f'<span class="gw-cl-text">{inline(entry.text, source, entry.line)}</span></li>'
            )
        out.append(f"{pad}</ul>")
        run.clear()

    for block in blocks:
        if isinstance(block, Entry):
            run.append(block)
        else:
            flush()
            out.append(
                f'{pad}<p class="gw-cl-note">{inline(block.text, source, block.line)}</p>'
            )
    flush()
    return out


PAGE_HTML = """<!doctype html>
<html lang="en" data-theme="dark">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <meta name="color-scheme" content="dark light" />
    <meta name="theme-color" content="#0b1014" media="(prefers-color-scheme: dark)" />
    <meta name="theme-color" content="#ffffff" media="(prefers-color-scheme: light)" />
    <meta name="description" content="glasswell release notes — what shipped in each version." />
    <link rel="icon" type="image/png" href="/favicon-32.png" />
    <link rel="stylesheet" href="/changelog/changelog.css" />
    <title>glasswell — changelog</title>
    <script src="/changelog/changelog.js"></script>
  </head>
  <body>
{body}
  </body>
</html>
"""

# Blocking, in <head>, and four lines long: the theme has to be on the element before the
# first paint or the reader watches the page change colour under them.
PAGE_JS = """(() => {
  const key = "glasswell.theme";
  const asked = new URLSearchParams(location.search).get("theme");
  let theme = asked === "light" || asked === "dark" ? asked : null;
  if (!theme) {
    try {
      const stored = localStorage.getItem(key);
      if (stored === "light" || stored === "dark") theme = stored;
    } catch {
      // A privacy-mode browser throws on access itself; dark is the app's default anyway.
    }
  }
  document.documentElement.dataset.theme = theme ?? "dark";
})();
"""

PAGE_CSS = """

*,
*::before,
*::after {
  box-sizing: border-box;
}

body {
  margin: 0;
  background: var(--ink);
  color: var(--paper);
  font-family: var(--gw-font-body);
  font-feature-settings: var(--gw-features);
  font-size: var(--gw-fs-body);
  line-height: 1.55;
}

:focus-visible {
  outline: 2px solid var(--cyan);
  outline-offset: 2px;
}

.gw-skip {
  position: absolute;
  left: -9999px;
  z-index: var(--gw-z-toast);
  padding: var(--gw-space-2) var(--gw-space-3);
  border-radius: var(--gw-radius-sm);
  background: var(--panel);
  color: var(--paper);
}

.gw-skip:focus {
  left: var(--gw-space-4);
  top: var(--gw-space-4);
}

.gw-cl-head {
  position: sticky;
  top: 0;
  z-index: var(--gw-z-panel);
  display: flex;
  align-items: center;
  gap: var(--gw-space-4);
  padding: var(--gw-rail-pad-y) var(--gw-rail-pad-x);
  background: var(--panel);
  border-bottom: 1px solid var(--hairline);
}

.gw-brand {
  display: flex;
  align-items: center;
  gap: var(--gw-space-2);
  color: var(--paper);
  text-decoration: none;
}

.gw-mark {
  width: 26px;
  height: 26px;
}

.gw-wordmark {
  font-family: var(--gw-font-display);
  font-size: 1.15rem;
  font-weight: var(--gw-fw-display);
  letter-spacing: var(--gw-ls-display);
}

.gw-wordmark-well {
  color: var(--cyan);
}

.gw-strap {
  margin: 0;
  color: var(--muted);
  font-family: var(--gw-font-display);
  font-size: var(--gw-fs-eyebrow);
  font-weight: var(--gw-fw-eyebrow);
  letter-spacing: var(--gw-ls-eyebrow);
  text-transform: uppercase;
}

.gw-cl-main {
  display: grid;
  grid-template-columns: 12rem minmax(0, 1fr);
  gap: var(--gw-space-5);
  align-items: start;
  max-width: 68rem;
  margin: 0 auto;
  padding: var(--gw-space-5) var(--gw-rail-pad-x) 4rem;
}

.gw-cl-main > h1,
.gw-cl-intro {
  grid-column: 1 / -1;
}

.gw-cl-main > h1 {
  margin: 0;
  font-family: var(--gw-font-display);
  font-size: var(--gw-fs-display);
  font-weight: var(--gw-fw-display);
  letter-spacing: var(--gw-ls-display);
}

.gw-cl-intro p {
  max-width: 46rem;
  margin: var(--gw-space-2) 0 0;
  color: var(--slate);
}

/* The rail is 41 px of band inside 8 px of padding; the nav clears it and nothing else. */
.gw-cl-nav {
  position: sticky;
  top: 4.25rem;
}

.gw-cl-navtitle {
  margin: 0 0 var(--gw-space-2);
  color: var(--muted);
  font-family: var(--gw-font-display);
  font-size: var(--gw-fs-eyebrow);
  font-weight: var(--gw-fw-eyebrow);
  letter-spacing: var(--gw-ls-eyebrow);
  text-transform: uppercase;
}

.gw-cl-nav ol {
  max-height: calc(100dvh - 9rem);
  margin: 0;
  padding: 0;
  overflow-y: auto;
  list-style: none;
  border-left: 1px solid var(--hairline);
}

.gw-cl-nav a {
  display: flex;
  justify-content: space-between;
  gap: var(--gw-space-2);
  margin-left: -1px;
  padding: 3px var(--gw-space-2);
  border-left: 2px solid transparent;
  color: var(--slate);
  font-family: var(--gw-font-mono);
  font-size: var(--gw-fs-mono);
  font-variant-numeric: tabular-nums;
  text-decoration: none;
}

.gw-cl-nav a:hover {
  border-left-color: var(--cyan);
  color: var(--paper);
}

.gw-cl-nav time {
  color: var(--muted);
}

/* The releases are a reading surface, so they sit on --panel and not on --ink: the palette's
   text-safe cousins (--cyan-text, --amber-text) are tuned against the panel, and on the ink
   background the light theme measured 4.32:1 for the version heading and the [New] tag. */
.gw-cl-releases {
  min-width: 0;
  padding: var(--gw-space-5);
  border: 1px solid var(--hairline);
  border-radius: var(--gw-radius-lg);
  background: var(--panel);
}

.gw-cl-rel {
  margin: 0 0 var(--gw-space-5);
}

.gw-cl-rel:last-child {
  margin-bottom: 0;
}

.gw-cl-rel > h2 {
  display: flex;
  align-items: baseline;
  gap: var(--gw-space-3);
  margin: 0 0 var(--gw-space-3);
  padding-bottom: var(--gw-space-2);
  border-bottom: 1px solid var(--hairline-strong);
  font-family: var(--gw-font-display);
  font-size: 1.3rem;
  font-weight: var(--gw-fw-display);
  letter-spacing: var(--gw-ls-display);
  scroll-margin-top: 5rem;
}

.gw-cl-ver {
  font-family: var(--gw-font-mono);
}

/* Cyan only where it sits on the panel. The same span in the nav is on --ink, where the
   light theme's --cyan-text measures 4.32:1; there it takes the link's own colour. */
.gw-cl-rel > h2 .gw-cl-ver {
  color: var(--cyan-text);
}

.gw-cl-date {
  color: var(--muted);
  font-family: var(--gw-font-mono);
  font-size: var(--gw-fs-mono);
  font-variant-numeric: tabular-nums;
  font-weight: 400;
  letter-spacing: 0;
}

.gw-cl-entries {
  display: grid;
  gap: var(--gw-space-2);
  margin: 0 0 var(--gw-space-4);
  padding: 0;
  list-style: none;
}

.gw-cl-entry {
  display: grid;
  grid-template-columns: 4.5rem minmax(0, 1fr);
  gap: var(--gw-space-3);
  align-items: baseline;
}

.gw-cl-tag {
  font-family: var(--gw-font-display);
  font-size: var(--gw-fs-eyebrow);
  font-weight: var(--gw-fw-eyebrow);
  letter-spacing: var(--gw-ls-eyebrow);
  text-align: right;
  text-transform: uppercase;
}

/* Category, not severity: cyan and amber are the two brand accents and nothing here is red.
   BRAND.md keeps red for gas, which is a data colour in this system. */
[data-tag="New"] .gw-cl-tag {
  color: var(--cyan-text);
}

[data-tag="Change"] .gw-cl-tag {
  color: var(--amber-text);
}

[data-tag="Fix"] .gw-cl-tag {
  color: var(--slate);
}

[data-tag="Remove"] .gw-cl-tag {
  color: var(--muted);
}

.gw-cl-text {
  min-width: 0;
}

.gw-cl-train {
  margin: 0 0 var(--gw-space-4);
}

.gw-cl-train > h3 {
  display: flex;
  align-items: baseline;
  gap: var(--gw-space-3);
  margin: 0 0 var(--gw-space-2);
  color: var(--slate);
  font-size: var(--gw-fs-title);
  font-weight: var(--gw-fw-title);
  letter-spacing: var(--gw-ls-title);
  scroll-margin-top: 5rem;
}

.gw-cl-note {
  max-width: 46rem;
  margin: 0 0 var(--gw-space-3);
  color: var(--slate);
}

.gw-cl-ref {
  color: var(--slate);
  font-family: var(--gw-font-mono);
  font-size: var(--gw-fs-mono);
}

/* The tint is what says "identifier"; the text stays --paper. Cyan on the composited tint
   measures 4.34:1 in the light theme, and a colour that has to be read is not a data colour. */
code {
  padding: 1px 4px;
  border-radius: var(--gw-radius-xs);
  background: var(--tint-accent);
  color: var(--paper);
  font-family: var(--gw-font-mono);
  font-size: var(--gw-fs-mono);
}

a {
  color: var(--cyan-text);
}

.gw-cl-foot {
  padding: var(--gw-space-4) var(--gw-rail-pad-x);
  border-top: 1px solid var(--hairline);
  color: var(--muted);
  font-size: var(--gw-fs-micro);
  text-align: center;
}

.gw-cl-foot p {
  margin: 0;
}

@media (max-width: 900px) {
  .gw-cl-main {
    grid-template-columns: minmax(0, 1fr);
  }

  .gw-cl-nav {
    position: static;
  }

  .gw-cl-nav ol {
    max-height: 11rem;
  }
}

@media (max-width: 620px) {
  .gw-cl-releases {
    padding: var(--gw-space-3);
  }

  .gw-cl-entry {
    grid-template-columns: minmax(0, 1fr);
    gap: 0;
  }

  .gw-cl-tag {
    text-align: left;
  }

  .gw-strap {
    display: none;
  }
}
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--changelog", type=Path, default=ROOT / "CHANGELOG.md")
    parser.add_argument("--style", type=Path, default=STYLE)
    parser.add_argument("--out", type=Path, default=ROOT / "web" / "dist" / "changelog")
    parser.add_argument("--check", action="store_true", help="parse only, write nothing")
    arguments = parser.parse_args(argv)

    doc = parse(arguments.changelog)
    page = render_html(doc, arguments.changelog)
    if arguments.check:
        releases = sum(1 for release in doc.releases if not release.empty)
        print(f"{arguments.changelog}: {releases} release(s), grammar clean")
        return 0

    arguments.out.mkdir(parents=True, exist_ok=True)
    (arguments.out / "index.html").write_text(page)
    (arguments.out / "changelog.css").write_text(render_css(arguments.style))
    (arguments.out / "changelog.js").write_text(PAGE_JS)
    print(f"{arguments.out}/index.html — {len(doc.releases)} section(s), {len(page)} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
