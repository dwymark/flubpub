"""Compose the four themed markdown files for the prototype.

Now that the CLI parses frontmatter on push/revise and the server lets
markdown indexes carry a theme, every page has the same shape:

    ---
    title: ...
    theme: 90s-academic
    color_scheme: parchment
    [index: ...]
    ---

    <style>...wallpaper bake + mobile strategy override...</style>

    body content from migration source

The CLI lifts theme/color_scheme/index out of the frontmatter; the server
treats markdown indexes as themed-with-list-substitution.
"""
from __future__ import annotations

from pathlib import Path

from bake_wallpaper import PAGES, page_css

SRC = Path("/tmp/flubpub-migration")
OUT = SRC / "themed"
OUT.mkdir(exist_ok=True)


# Per-page frontmatter. The body comes verbatim from the migration source
# (with any source-side frontmatter stripped).
RECIPES: dict[str, dict] = {
    "home": {
        "src": SRC / "home.md",
        "frontmatter": {
            "title": "Daniel Wymark",
            "theme": "90s-academic",
            "color_scheme": "parchment",
            "index": {
                "filter": {"slug_regex": "^(research|tidbits)$"},
                "sort": {"by": "manual", "manual": ["research", "tidbits"]},
            },
        },
    },
    "research": {
        "src": SRC / "research.md",
        "frontmatter": {
            "title": "Research & Publications",
            "theme": "90s-academic",
            "color_scheme": "parchment",
        },
    },
    "tidbits": {
        "src": SRC / "tidbits.md",
        "frontmatter": {
            "title": "Tidbits",
            "theme": "90s-academic",
            "color_scheme": "parchment",
            "index": {
                "filter": {"parent": "tidbits"},
                "sort": {"by": "title", "order": "asc"},
            },
        },
    },
    "polar-plots": {
        "src": SRC / "polar-plots.md",
        "frontmatter": {
            "title": "Prime Number Polar Plots",
            "theme": "90s-academic",
            "color_scheme": "parchment",
        },
    },
}


def yaml_dump(d: dict, indent: int = 0) -> str:
    """Tiny hand-rolled YAML emitter sufficient for our shapes."""
    pad = "  " * indent
    out: list[str] = []
    for k, v in d.items():
        if isinstance(v, dict):
            out.append(f"{pad}{k}:")
            out.append(yaml_dump(v, indent + 1))
        elif isinstance(v, list):
            inline = ", ".join(f'"{x}"' if isinstance(x, str) else str(x) for x in v)
            out.append(f"{pad}{k}: [{inline}]")
        elif isinstance(v, str):
            needs_quote = any(c in v for c in ":#&*!|>%@`") or v.startswith("^")
            out.append(f'{pad}{k}: {("\"" + v + "\"") if needs_quote else v}')
        else:
            out.append(f"{pad}{k}: {v}")
    return "\n".join(out)


def strip_frontmatter(text: str) -> str:
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end != -1:
            return text[end + 5:]
    return text


def compose(slug: str) -> Path:
    page_spec = next(p for p in PAGES if p["slug"] == slug)
    recipe = RECIPES[slug]
    body = strip_frontmatter(recipe["src"].read_text(encoding="utf-8")).lstrip("\n")
    fm = yaml_dump(recipe["frontmatter"])
    style_block = page_css(page_spec)
    composed = f"---\n{fm}\n---\n\n{style_block}\n\n{body}"
    out = OUT / f"{slug}.md"
    out.write_text(composed, encoding="utf-8")
    return out


if __name__ == "__main__":
    for slug in RECIPES:
        path = compose(slug)
        size_kb = path.stat().st_size / 1024
        print(f"  {slug:14s} -> {path}  ({size_kb:.1f} KB)")
