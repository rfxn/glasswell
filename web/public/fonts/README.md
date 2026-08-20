# Self-hosted brand faces

Same-origin only. No font CDN, no `@import`, no third-party request at runtime —
the app is served behind Cloudflare Access and a font request to `fonts.gstatic.com`
would leak a page view to an origin the reader never agreed to.

| File | Source | Upstream sha256 | Licence |
|---|---|---|---|
| `inter-var-latin.woff2` | Inter 4.1 `InterVariable.ttf` | `4989b125924991b90d05b2d16e0e388c48f7d5bb8b30539bbf9c755278d0ccaf` | SIL OFL 1.1 (`OFL-Inter.txt`) |
| `jetbrains-mono-var-latin.woff2` | JetBrains Mono 2.304 `JetBrainsMono[wght].ttf` | `662a196d58f1183bf2d77428b6d5283fe3f45161ab021bea4036bc98e5cac016` | SIL OFL 1.1 (`OFL-JetBrainsMono.txt`) |
| `gw-symbols.woff2` | JetBrains Mono 2.304, two codepoints only | same as above | SIL OFL 1.1 (`OFL-JetBrainsMono.txt`) |

Neither upstream licence declares a Reserved Font Name, so subsetting and
redistribution under the OFL are permitted; both licence files ship beside the
fonts because OFL §2 requires it.

`gw-symbols.woff2` exists because Inter has no glyph for `U+233E ⌾` — the explain
affordance the product uses in prose, in the help panel and on every figure — nor
for `U+2715 ✕`. It is declared under the same CSS family names with a two-codepoint
`unicode-range`, so those characters render from a brand face instead of falling
back to whatever the reader's system supplies.

`U+FF0B ＋` (`web/src/map/pills.ts`) is in neither face and still falls back.

## Regenerating

```bash
curl -sSL -o /tmp/inter.zip   https://github.com/rsms/inter/releases/download/v4.1/Inter-4.1.zip
curl -sSL -o /tmp/jbmono.zip  https://github.com/JetBrains/JetBrainsMono/releases/download/v2.304/JetBrainsMono-2.304.zip
unzip -q /tmp/inter.zip -d /tmp/inter && unzip -q /tmp/jbmono.zip -d /tmp/jbmono

SANS="U+0020-007E,U+00A0-00FF,U+0100-017F,U+2000-206F,U+2122,U+2190-2193,U+2212,U+2260,U+2264,U+2265,U+25A0-25CF,U+FEFF"
MONO="U+0020-007E,U+00A0-00FF,U+2000-206F,U+2212,U+FEFF"

pyftsubset /tmp/inter/InterVariable.ttf --output-file=inter-var-latin.woff2 --flavor=woff2 \
  --unicodes="$SANS" --layout-features='kern,calt,ccmp,liga,locl,mark,mkmk,case,tnum,zero,cv05,cv08' --recalc-bounds
pyftsubset "/tmp/jbmono/fonts/variable/JetBrainsMono[wght].ttf" --output-file=jetbrains-mono-var-latin.woff2 \
  --flavor=woff2 --unicodes="$MONO" --layout-features='kern,ccmp,mark,mkmk' --recalc-bounds
pyftsubset "/tmp/jbmono/fonts/variable/JetBrainsMono[wght].ttf" --output-file=gw-symbols.woff2 \
  --flavor=woff2 --unicodes="U+233E,U+2715" --layout-features='' --recalc-bounds
```

Both axes of Inter are retained (`opsz` 14–32, `wght` 100–900): one file covers every
weight the chrome uses, and the optical-size axis is what keeps 11 px status text and
a 24 px wordmark from being the same letterform scaled.

`tnum` and `zero` are kept because this app is mostly numbers; `cv05` (tailed `l`) and
`cv08` (serifed `I`) are kept and enabled because `l`/`I`/`1` collide in operator names
and API-10s. Ligatures are dropped from the mono subset on purpose — `==` and `->`
occur inside derivation handles, and a ligature there misreports the string.
