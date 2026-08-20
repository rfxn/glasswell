# glasswell — Brand Spec

Source of truth for the glasswell visual system. All marks are hand-authored SVG
in `assets/`; the PNG and ICO files in `assets/brand/` are rendered derivatives,
not originals. Regenerate them with the commands at the bottom of this file.

---

## Name & wordmark

- **Name:** glasswell — one word, always lowercase, including at the start of a
  sentence. Never "GlassWell", "Glass Well", or "GLASSWELL".
- **Wordmark:** `glass` in the foreground text colour, `well` in glass cyan. The
  split is the thesis: the box is transparent, the object inside it is a well.
- **Former name:** basinforge, retained as a repo alias so prior notes resolve.
  It is not a brand and gets no assets.
- **Tagline (primary):** Glass-box upstream analytics on public data
- **Strapline:** no naked numbers · every figure traces to a checksummed regulator file

## Logo mark

A wellbore traced inside a glass panel: surface location, vertical section,
kickoff, and a horizontal lateral with three perforation clusters. A dashed line
across the panel is the target formation top.

| Element | Means |
|---------|-------|
| Glass panel + sheen | The glass box — the interior is visible by construction |
| Amber wellbore | The domain object, and the only warm colour in the system |
| Cyan surface node + perf ticks | The instrumented, measured parts |
| Dashed formation top | Subsurface context, drawn but not asserted |

## Colour

| Hex | Name | Role |
|-----|------|------|
| `#0B1014` | Ink | Dark background, app-icon tile |
| `#121A21` | Panel | Dark surface |
| `#5FD3E8` | Glass cyan | Primary accent on dark; wordmark `well`; links |
| `#2A9BB5` | Deep cyan | Primary accent on light; diagram canonical layer |
| `#E4A33C` | Amber | The wellbore; raw / immutable / manifest surfaces |
| `#B57A18` | Deep amber | Amber on light backgrounds; quarantine and audit |
| `#E6EDF3` | Paper | Text on dark |
| `#9FB0BC` | Slate light | Secondary text on dark |
| `#55666F` | Slate | Secondary text on light |
| `#7C8B96` | Muted | Tertiary text, hairlines |
| `#D8E1E8` | Border light | Diagram frames and dividers |

**Stream colours** follow the petroleum industry convention, not the brand
palette, because the audience reads them as data before they read them as design:

| Stream | Dark | Light |
|--------|------|-------|
| Oil | `#3FA55E` | `#2F8A4B` |
| Gas | `#D9534F` | `#C0392B` |
| Water | `#3D8BD4` | `#2C74B8` |

Gas red is a data colour here, not an alert colour. Nothing in this system uses
red for severity, so there is no signal to dilute.

## Typography

System sans (`system-ui` stack) for everything, `ui-monospace` for identifiers,
endpoints, hashes, and table names. No vendored fonts and no font loading: the
diagrams have to render identically in a GitHub markdown preview, a terminal
image viewer, and a PDF export.

The wordmark is live text rather than outlined paths, so it degrades gracefully
to whatever sans the reader has. If a fixed letterform ever matters, render the
PNG lockup instead of embedding the SVG.

## Assets

| File | Use |
|------|-----|
| `assets/logo-mark.svg` | Icon with the ink tile — app icon, avatar, anything ≥64 px |
| `assets/logo-mark-small.svg` | Simplified mark for ≤48 px: no formation top, no perf ticks, thicker strokes. Favicons render from this |
| `assets/logo-icon.svg` | Tile-less mark for light surfaces and watermarks |
| `assets/logo-horizontal-dark.svg` | Primary lockup on dark |
| `assets/logo-horizontal-light.svg` | Primary lockup on light |
| `assets/banner-dark.svg` · `banner-light.svg` | README and docs header |
| `assets/og-card.svg` · `og-card.png` | Social / share card, 1200×630 |
| `assets/architecture.svg` | System architecture, layer by layer |
| `assets/lineage.svg` | The glass-box chain from a number to raw bytes |
| `assets/forecast-to-dollars.svg` | Modelling pipeline and its control group |
| `assets/roadmap.svg` | Build phases with exit criteria |
| `assets/brand/*` | Rendered PNG / ICO derivatives |

Clear space around the mark is the width of one perforation tick. Do not
recolour, stretch, rotate, add effects, or place the mark on a background that
puts the cyan panel edge below 3:1 contrast.

## Diagram conventions

Every diagram uses an explicit white canvas so it reads in both GitHub themes,
carries a `role="img"` and an `aria-label` describing its content, and colours
its bands by layer: neutral for source and raw, pale blue-grey for staging, cyan
for canonical, green for marts and serving, amber for quarantine and audit.

## Regenerating derivatives

```bash
rsvg-convert -w 1200 -h 630 assets/og-card.svg          -o assets/og-card.png
rsvg-convert -w 512        assets/logo-mark.svg         -o assets/brand/app-icon-512.png
rsvg-convert -w 180        assets/logo-mark.svg         -o assets/brand/favicon-180.png

# Small sizes render from the simplified mark — the dashed formation top and the
# perf ticks turn to noise below ~48 px.
rsvg-convert -w 32         assets/logo-mark-small.svg   -o assets/brand/favicon-32.png
rsvg-convert -w 256        assets/logo-mark-small.svg   -o /tmp/mark-small256.png
magick /tmp/mark-small256.png -define icon:auto-resize=64,48,32,16 assets/brand/favicon.ico
rsvg-convert -w 1320       assets/logo-horizontal-dark.svg  -o assets/brand/logo-horizontal-dark.png
rsvg-convert -w 1320       assets/logo-horizontal-light.svg -o assets/brand/logo-horizontal-light.png
rsvg-convert -w 2400 -h 680 assets/banner-dark.svg      -o assets/brand/banner-dark.png
```

---

> Copyright (C) 2026 R-fx Networks &lt;proj@rfxn.com&gt; &#183; Ryan MacDonald &#183; Licensed under GNU GPL v2
