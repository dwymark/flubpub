"""Render canonical prose+SVG content through every papered theme and
assemble a side-by-side iframe grid for visual comparison.

Run from the project root:
    uv run python3 scratch/preview-papered/build_preview.py

Then serve over HTTP per CLAUDE.md (file:// breaks relative paths):
    cd scratch/preview-papered && python3 -m http.server 8765
    wslview http://localhost:8765/
"""
from __future__ import annotations

from pathlib import Path

import markdown as md_lib

from flubpub.server import render_themed_page

# The ten papered themes, ordered roughly light->mid->dark for the grid.
PAPERED_THEMES = [
    "folio",
    "alpine",
    "engineroom",
    "latticework",
    "meadow",
    "harbor",
    "kiln",
    "ember",
    "quarry",
    "nocturne",
]

# One-line ethos blurbs for the grid index.
ETHOS = {
    "folio":       "Quietly bookish. Warm parchment, walnut ink, drifting waves.",
    "alpine":      "Cool crisp mathematical. Snow paper, slate type, three-fold curls.",
    "engineroom":  "Technical-paper. Off-black on cream, crosshair grid.",
    "latticework": "Bauhaus mathematical. Ink-and-teal, four-fold quatrefoil.",
    "meadow":      "Botanical. Sage paper, leaf-green accents, gentle basket weave.",
    "harbor":      "Nautical journal. Buff card on navy ink, rust-mark beacon.",
    "kiln":        "Warm ceramic. Clay glaze, ember accent, six-fold snowflake.",
    "ember":       "Dark mode reading. Charcoal-and-rust, curved truchet arcs.",
    "quarry":      "Geological. Basalt with ochre veins, cmm diamonds.",
    "nocturne":    "Scholarly dark. Deep midnight, silver-gold, Penrose rhombi.",
}

# The canonical sample exercises every prose element a papered page is
# expected to handle gracefully: lede, h2/h3, blockquote, inline code,
# fenced code, table, list, link, hr fleuron, and a small mathy SVG.
SAMPLE_MD = r"""
What I'm thinking about lately, in roughly the shape it actually arrives.
Not a manifesto, just notes that hold together long enough to publish.

The idea I keep returning to is that **structure precedes content**: the
mold you set decides what kind of writing you can pour into it. So I've
been redesigning the molds.

## On reading rooms

A page is a place. The most useful question to ask of a layout is not
*does it look good*, but *is this somewhere I can sit for a while*. The
answer almost always turns on three small choices: measure (how long the
line is), leading (how much air is between lines), and the relationship
of the figure to the ground.

> Value carries hierarchy. Hue carries identity. Saturation carries mood.
> If a color in your design is doing none of those three jobs, ask why
> it's there.

### A worked example

Here's a tiny [Möbius transformation](https://en.wikipedia.org/wiki/M%C3%B6bius_transformation)
drawn directly into the markdown, no asset upload needed:

<figure>
<svg viewBox="0 0 320 160" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Möbius circles">
  <defs>
    <radialGradient id="mob" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="var(--accent)" stop-opacity="0.35"/>
      <stop offset="100%" stop-color="var(--accent)" stop-opacity="0"/>
    </radialGradient>
  </defs>
  <g fill="none" stroke="currentColor" stroke-width="1.2">
    <circle cx="80"  cy="80" r="56"/>
    <circle cx="80"  cy="80" r="40"/>
    <circle cx="80"  cy="80" r="24"/>
    <circle cx="80"  cy="80" r="10"/>
    <circle cx="240" cy="80" r="56"/>
    <circle cx="240" cy="80" r="40"/>
    <circle cx="240" cy="80" r="24"/>
    <circle cx="240" cy="80" r="10"/>
    <line x1="24" y1="80" x2="296" y2="80" stroke-dasharray="2 4"/>
  </g>
  <circle cx="160" cy="80" r="42" fill="url(#mob)"/>
</svg>
<figcaption>A pair of orthogonal circle pencils under inversion.</figcaption>
</figure>

A snippet of the kind of thing I'd actually write inline:

```python
def mobius(z, a, b, c, d):
    # Möbius transformation; determinant ad - bc must be nonzero.
    return (a * z + b) / (c * z + d)
```

Or referred to as `mobius(z, 1, 0, 0, 1)` — the identity.

## A small index

| Year | Idea                                  | Status     |
|------|---------------------------------------|------------|
| 2019 | Vuza canons in colored Cayley graphs  | published  |
| 2022 | Generative fragment shaders           | recurring  |
| 2024 | Embedded telescope control            | day job    |
| 2026 | Wallpapered reading rooms             | in flight  |

What the grid should make obvious is that none of these are unrelated.
They share a common thread of *constraints make structure visible*.

---

Anyway. Three concrete next steps:

1. Pick a wallpaper that recedes, not advances.
2. Set the measure first; everything else follows.
3. Don't let the chrome eat the content.

A small sample of an index list rendered server-side:

<ul class="flubpub-pages">
  <li><a href="#">Vuza canons</a> <small class="flubpub-date">2019-08-12</small><div class="flubpub-excerpt">Tiling the integers without periodic factors.</div></li>
  <li><a href="#">Polar plots</a> <small class="flubpub-date">2022-03-04</small><div class="flubpub-excerpt">Live-rendered orbits in r=f(θ) form.</div></li>
  <li><a href="#">Fragment shader notes</a> <small class="flubpub-date">2023-11-22</small></li>
</ul>
"""


def render_sample(theme: str) -> str:
    body_html = md_lib.markdown(
        SAMPLE_MD,
        extensions=["extra", "sane_lists", "tables"],
        output_format="html5",
    )
    wrapped = f'<div class="markdown-content">{body_html}</div>'
    return render_themed_page(
        theme=theme,
        slug=f"preview-{theme}",
        title=f"Reading room ({theme})",
        content=wrapped,
        date="2026-05-10",
        color_scheme=None,  # use the theme default
    )


INDEX_CSS = """
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  max-width: 56ch;
  margin: 3rem auto;
  padding: 0 1rem;
  line-height: 1.55;
  color: #222;
}
h1 { font-size: 1.4rem; margin: 0 0 0.5rem; }
p.lede { color: #555; margin: 0 0 1.5rem; }
ol { list-style: none; padding: 0; margin: 0; }
ol li {
  padding: 0.55rem 0;
  border-bottom: 1px solid #eee;
  display: flex;
  gap: 1rem;
  align-items: baseline;
}
ol li a { font-weight: 600; color: #1d4ed8; text-decoration: none; min-width: 9ch; }
ol li a:hover { text-decoration: underline; }
ol li .ethos { color: #555; font-size: 0.95em; }
"""


def build_index(out_dir: Path) -> None:
    rows = []
    for theme in PAPERED_THEMES:
        rows.append(
            f'  <li><a href="{theme}/index.html">{theme}</a>'
            f'<span class="ethos">{ETHOS[theme]}</span></li>'
        )
    html = f"""<!DOCTYPE html>
<html><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Papered themes preview</title>
<style>{INDEX_CSS}</style>
</head><body>
<h1>Papered themes</h1>
<p class="lede">Same canonical prose+SVG sample rendered through each of the
ten papered themes. Open one in a new tab to see the wallpaper layer at
full window.</p>
<ol>
{chr(10).join(rows)}
</ol>
</body></html>"""
    (out_dir / "index.html").write_text(html)


def main() -> None:
    out_dir = Path(__file__).parent
    for theme in PAPERED_THEMES:
        target = out_dir / theme
        target.mkdir(exist_ok=True)
        rendered = render_sample(theme)
        (target / "index.html").write_text(rendered)
        print(f"  wrote {target.relative_to(out_dir.parent.parent)}/index.html")
    build_index(out_dir)
    print(f"\nGrid index: {(out_dir / 'index.html').relative_to(out_dir.parent.parent)}")


if __name__ == "__main__":
    main()
