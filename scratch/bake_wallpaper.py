"""Bake a tiling-catalog SVG into a data: URI with chosen colors.

Replaces every `var(--tiling-bg, ...)`, `var(--tiling-fg, ...)`, etc. and the
internal <style> declaration with literal hex values, then URL-encodes the
SVG and returns a `data:image/svg+xml,...` string suitable for a CSS
`background-image`.

This avoids the gotcha that browsers do NOT resolve `var()` against the
consuming element when an SVG is referenced as a background image — they
resolve against the SVG's own root computed style. Pre-baking is the
documented workaround.
"""
from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import quote

TILINGS = Path(
    "/home/dwymark/.claude/skills/style/web/tilings/patterns"
)


def bake(
    pattern_path: Path,
    *,
    bg: str = "transparent",
    fg: str = "#222222",
    accent_1: str | None = None,
    accent_2: str | None = None,
    opacity: float = 1.0,
    stroke_width: float = 1.5,
    tile_size: int = 256,
) -> str:
    """Read a catalog SVG and return a data:image/svg+xml URI with colors baked in."""
    accent_1 = accent_1 or fg
    accent_2 = accent_2 or accent_1

    raw = pattern_path.read_text(encoding="utf-8")

    # Replace the inner <style>{...} declaration so the SVG's computed-style
    # defaults match our overrides. The default declaration looks like:
    #   svg{--tiling-bg:transparent;--tiling-fg:#222222;...}
    new_decl = (
        f"svg{{"
        f"--tiling-bg:{bg};"
        f"--tiling-fg:{fg};"
        f"--tiling-accent-1:{accent_1};"
        f"--tiling-accent-2:{accent_2};"
        f"--tiling-opacity:{opacity};"
        f"--tiling-stroke-width:{stroke_width};"
        f"}}"
    )
    raw = re.sub(r"svg\{[^}]*\}", new_decl, raw, count=1)

    # Strip XML prolog and HTML comments — neither is needed in a data URI and
    # they bloat the encoding.
    raw = re.sub(r"<\?xml[^?]*\?>\s*", "", raw)
    raw = re.sub(r"<!--.*?-->\s*", "", raw, flags=re.DOTALL)
    raw = raw.strip()

    # URL-encode. Critical: `<`, `>`, `"` and `#` MUST be encoded.
    #   - Literal `<`/`>` cause the outer <style> element to terminate at any
    #     `</style>` token inside the encoded SVG.
    #   - Literal `"` terminates the CSS `url("...")` string.
    #   - Literal `#` would be read as a URL fragment delimiter.
    # Everything else is left readable to keep the URI compact.
    encoded = quote(raw, safe="=:;,/[]()' ")
    return f"data:image/svg+xml;utf8,{encoded}"


# Color palette for the academic-modern look — cream paper, walnut ink,
# muted teal accent. These get fed in per-page below.
PALETTE = {
    "paper":        "#f4ecd8",
    "paper_dark":   "#e6dcc1",
    "ink":          "#3a342b",
    "ink_light":    "#6a5f4d",
    "rule":         "#c8b89a",
    "accent":       "#5a7a7a",  # muted teal
    "accent_warm":  "#a05a3a",  # warm rust
}


PAGES = [
    {
        "slug": "home",
        "pattern": TILINGS / "p1" / "p1-drift.svg",
        "strategy": "wp-peek",
        "fg": PALETTE["accent"],
        "opacity": 0.35,
        "stroke_width": 1.2,
        "tile_px": 220,
    },
    {
        "slug": "research",
        "pattern": TILINGS / "pmm" / "pmm-grid.svg",
        "strategy": "wp-band",
        "fg": PALETTE["ink_light"],
        "opacity": 0.45,
        "stroke_width": 1.0,
        "tile_px": 180,
    },
    {
        "slug": "tidbits",
        "pattern": TILINGS / "p4m" / "p4m-quatrefoil.svg",
        "strategy": "wp-translucent",
        "fg": PALETTE["accent_warm"],
        "opacity": 0.55,
        "stroke_width": 1.3,
        "tile_px": 200,
    },
    {
        "slug": "polar-plots",
        "pattern": TILINGS / "non-period" / "truchet" / "truchet.svg",
        "strategy": "wp-stamp",
        "fg": PALETTE["ink"],
        "opacity": 0.85,
        "stroke_width": 1.4,
        "tile_px": 180,
    },
]


def page_css(page: dict) -> str:
    """Build the inline <style> block for a page given its bake spec."""
    uri = bake(
        page["pattern"],
        bg="transparent",
        fg=page["fg"],
        opacity=page["opacity"],
        stroke_width=page["stroke_width"],
    )
    tile = page["tile_px"]
    strategy = page["strategy"]

    # Common: set the wallpaper as the page background.
    base = f"""body {{
  --page-wallpaper: url("{uri}");
  --page-wallpaper-tile: {tile}px;
  background-image: var(--page-wallpaper);
  background-size: var(--page-wallpaper-tile);
  background-repeat: repeat;
  background-attachment: fixed;
}}
"""

    # Per-strategy mobile overrides. Theme defaults to wp-peek; only emit
    # overrides for the other three.
    if strategy == "wp-peek":
        mobile = ""  # theme default works
    elif strategy == "wp-band":
        mobile = """@media (max-width: 720px) {
  body { background-image: none; background-color: var(--bg); }
  body::before {
    content: "";
    display: block;
    height: 32vh;
    background-image: var(--page-wallpaper);
    background-size: var(--page-wallpaper-tile);
    background-repeat: repeat;
    border-bottom: 2px solid var(--rule, #c8b89a);
    box-shadow: inset 0 -10px 20px -10px rgba(0,0,0,0.15);
  }
  main { margin: 0; padding-top: 1.5rem; box-shadow: none; border: none; }
}
"""
    elif strategy == "wp-translucent":
        mobile = """@media (max-width: 720px) {
  /* full-bleed wallpaper, content card semi-transparent */
  main {
    margin: 1rem 0.5rem;
    background: rgba(244, 236, 216, 0.88);
    backdrop-filter: blur(2px);
    border: 1px solid var(--rule, #c8b89a);
    box-shadow: 0 2px 12px rgba(0,0,0,0.08);
  }
}
"""
    elif strategy == "wp-stamp":
        mobile = """@media (max-width: 720px) {
  /* hide the page-bg wallpaper; show only as a small stamp beside the title */
  body { background-image: none; background-color: var(--bg); }
  main { margin: 0; padding: 1rem; box-shadow: none; border: none; }
  h1 {
    display: grid;
    grid-template-columns: 64px 1fr;
    gap: 0.75rem;
    align-items: center;
  }
  h1::before {
    content: "";
    width: 64px; height: 64px;
    background-image: var(--page-wallpaper);
    background-size: var(--page-wallpaper-tile);
    background-repeat: repeat;
    border: 1.5px solid var(--rule, #c8b89a);
    border-radius: 4px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.1);
  }
}
"""
    else:
        mobile = ""

    return f"<style>\n{base}{mobile}</style>"


if __name__ == "__main__":
    import json
    out = {p["slug"]: page_css(p) for p in PAGES}
    print(json.dumps(out, indent=2))
