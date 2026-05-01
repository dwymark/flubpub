import json
import logging
import os
import re
import subprocess
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, PackageLoader
from pydantic import BaseModel

import markdown as md_lib

from flubpub.colors import DEFAULT_SCHEMES, available_color_schemes, color_scheme_css, get_color_scheme
from flubpub.index_payload import (
    build_index_payload,
    parse_index_spec_from_html,
    parse_index_spec_from_markdown,
    substitute_pages_marker,
)
from flubpub.models import IndexSpec, PageCreate, PageDetail, PageResponse, PageUpdate

logger = logging.getLogger(__name__)

DATA_DIR = Path(os.environ.get("FLUBPUB_DATA_DIR", "./data"))
SITE_DIR = Path(os.environ.get("FLUBPUB_SITE_DIR", "./site"))
PAGES_DIR = SITE_DIR / "src" / "pages"
PAGES_JSON = DATA_DIR / "pages.json"
SITE_OUTPUT = SITE_DIR / "_site"
ASSETS_DIR = SITE_DIR / "src" / "assets"
THEMES_DIR = Path(__file__).parent / "themes"
CUSTOM_INDEX_SRC = DATA_DIR / "custom_index.html"
CUSTOM_INDEX_SPEC = DATA_DIR / "custom_index_spec.json"
INDEX_PAGES_MARKER_ID = "flubpub-pages"

# Sentinel substituted with a server-rendered HTML <ul> of the index payload.
# Survives markdown-it as either a bare comment or wrapped in <p>…</p>.
LIST_SENTINEL = "<!--FLUBPUB-LIST-->"
_LIST_SENTINEL_RE = re.compile(
    r"(<p>\s*)?" + re.escape(LIST_SENTINEL) + r"(\s*</p>)?",
    re.IGNORECASE,
)


def _render_pages_list_html(payload: list[dict]) -> str:
    """Render an index payload as a simple <ul>. Handles both flat lists and
    grouped {label, pages} sections. Inline-styled, no theme — callers can
    override with their own template if they want richer presentation."""
    if not payload:
        return '<p class="flubpub-empty">No pages yet.</p>'

    def _date(p: dict) -> str:
        v = p.get("created_at") or ""
        return v[:10] if isinstance(v, str) and len(v) >= 10 else ""

    def _li(p: dict) -> str:
        title = p.get("title") or p.get("slug") or "(untitled)"
        url = p.get("url") or f"/{p.get('slug', '')}/"
        date = _date(p)
        excerpt = p.get("excerpt")
        bits = [f'<a href="{url}">{title}</a>']
        if date:
            bits.append(f' <small class="flubpub-date">{date}</small>')
        if excerpt:
            bits.append(f'<div class="flubpub-excerpt">{excerpt}</div>')
        return f'<li>{"".join(bits)}</li>'

    grouped = payload and isinstance(payload[0], dict) and "pages" in payload[0] and "label" in payload[0]
    if grouped:
        sections = []
        for sec in payload:
            items = "\n  ".join(_li(p) for p in sec.get("pages") or [])
            sections.append(
                f'<section class="flubpub-section">'
                f'<h2>{sec.get("label", "")}</h2>'
                f'<ul class="flubpub-pages">\n  {items}\n</ul></section>'
            )
        return "\n".join(sections)

    items = "\n  ".join(_li(p) for p in payload)
    return f'<ul class="flubpub-pages">\n  {items}\n</ul>'


def _substitute_list_sentinel(html: str, payload: list[dict]) -> str:
    """Replace the first occurrence of LIST_SENTINEL (and any wrapping <p>)
    with a server-rendered list. Returns html unchanged if no sentinel."""
    if LIST_SENTINEL not in html:
        return html
    rendered = _render_pages_list_html(payload)
    return _LIST_SENTINEL_RE.sub(lambda _m: rendered, html, count=1)


def _render_markdown_to_html(md_text: str) -> str:
    """Render markdown to HTML using a small extension set. Used for the
    root index when the operator pushes a .md instead of an .html."""
    return md_lib.markdown(
        md_text,
        extensions=["extra", "sane_lists", "tables"],
        output_format="html5",
    )

jinja_env = Environment(loader=PackageLoader("flubpub", "themes"))


def available_themes() -> list[str]:
    return [f.stem for f in THEMES_DIR.glob("*.html")]


def resolve_color_scheme(theme: str, color_scheme: str | None) -> str:
    return color_scheme or DEFAULT_SCHEMES.get(theme, "clean")


def render_themed_page(theme: str, slug: str, title: str, content: str, date: str,
                       color_scheme: str | None = None) -> str:
    template = jinja_env.get_template(f"{theme}.html")
    html = template.render(title=title, content=content, date=date, slug=slug)
    scheme = resolve_color_scheme(theme, color_scheme)
    css_block = color_scheme_css(scheme)
    # Inject color scheme CSS vars right after <head>
    html = html.replace("<head>", f"<head>\n  {css_block}", 1)
    return html


def write_page_file(slug: str, title: str, content: str, date: str,
                    theme: str | None, color_scheme: str | None = None,
                    content_type: str = "markdown") -> None:
    """Write the page file. Themed → Jinja2 wrap + .html, raw HTML → .html verbatim,
    otherwise .md. Cleans up the other format on each write.

    When `theme` is set and `content_type == "markdown"`, the content is
    pre-rendered to HTML and wrapped in `<div class="markdown-content">`
    before being passed to the theme — themes expect HTML, not raw markdown.
    """
    old_md, old_html = PAGES_DIR / f"{slug}.md", PAGES_DIR / f"{slug}.html"
    if theme:
        if content_type == "markdown":
            content = (
                f'<div class="markdown-content">'
                f'{_render_markdown_to_html(content)}'
                f'</div>'
            )
        rendered = render_themed_page(theme, slug, title, content, date, color_scheme)
        fm = f'---\ntitle: "{title}"\ndate: "{date}"\nlayout: false\n---\n{rendered}\n'
        old_html.write_text(fm)
        old_md.unlink(missing_ok=True)
    elif content_type == "html_raw":
        fm = f'---\ntitle: "{title}"\ndate: "{date}"\nlayout: false\n---\n{content}\n'
        old_html.write_text(fm)
        old_md.unlink(missing_ok=True)
    else:
        fm = f'---\ntitle: "{title}"\ndate: "{date}"\n---\n{content}\n'
        old_md.write_text(fm)
        old_html.unlink(missing_ok=True)


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9-]+", "", text.lower().replace(" ", "-"))


def rebuild_site(site_dir: Path) -> None:
    try:
        subprocess.run(["npx", "@11ty/eleventy"], cwd=site_dir, check=True)
    except FileNotFoundError:
        logger.warning("npx not found; skipping 11ty build")
    except subprocess.CalledProcessError as e:
        logger.warning("11ty build failed: %s", e)
    inject_custom_index()


def _inject_marker(html: str, spec: IndexSpec, all_pages: list[dict], self_slug: str) -> str:
    """Substitute both index seams in `html` with the personalized payload for
    `spec`: the JSON `<script id="flubpub-pages">` marker (used by template-
    driven indexes), and the `<!--FLUBPUB-LIST-->` sentinel (used by prose-
    headed markdown indexes for a server-rendered <ul>). Either or both may
    be absent — each substitution is a no-op when its target isn't found."""
    payload = build_index_payload(spec, all_pages, self_slug)
    payload_json = json.dumps(payload, indent=2, default=str)
    html = substitute_pages_marker(html, payload_json)
    html = _substitute_list_sentinel(html, payload)
    return html


def inject_index_pages() -> None:
    """For every index page (content_type=='index' in pages.json, plus the
    legacy root index backed by data/custom_index.html), substitute the
    #flubpub-pages marker with that page's personalized payload and write the
    result back to _site."""
    all_pages = load_pages(DATA_DIR)

    for entry in all_pages:
        if entry.get("content_type") != "index":
            continue
        out_path = SITE_OUTPUT / entry["slug"] / "index.html"
        if not out_path.exists():
            continue
        try:
            spec = IndexSpec(**(entry.get("index") or {}))
        except Exception as e:
            logger.warning("Bad index spec for %s: %s", entry["slug"], e)
            continue
        html = out_path.read_text()
        html = _inject_marker(html, spec, all_pages, self_slug=entry["slug"])
        out_path.write_text(html)

    if CUSTOM_INDEX_SRC.exists():
        try:
            html = CUSTOM_INDEX_SRC.read_text()
        except OSError as e:
            logger.warning("Could not read custom index source: %s", e)
            return
        SITE_OUTPUT.mkdir(parents=True, exist_ok=True)
        # The root index optionally carries a sidecar IndexSpec written by
        # set_custom_index. When absent, fall back to the empty default
        # (sorted-newest-first) for backwards compatibility.
        spec = IndexSpec()
        if CUSTOM_INDEX_SPEC.exists():
            try:
                spec = IndexSpec(**json.loads(CUSTOM_INDEX_SPEC.read_text()))
            except Exception as e:
                logger.warning("Bad sidecar root-index spec: %s", e)
        html = _inject_marker(html, spec, all_pages, self_slug="")
        (SITE_OUTPUT / "index.html").write_text(html)


def inject_custom_index() -> None:
    """Backwards-compat alias. Existing callers keep working."""
    inject_index_pages()


def load_pages(data_dir: Path) -> list[dict]:
    path = data_dir / "pages.json"
    if not path.exists():
        return []
    return json.loads(path.read_text())


def save_pages(data_dir: Path, pages: list[dict]) -> None:
    (data_dir / "pages.json").write_text(json.dumps(pages, indent=2, default=str))


@asynccontextmanager
async def lifespan(app: FastAPI):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PAGES_DIR.mkdir(parents=True, exist_ok=True)
    SITE_OUTPUT.mkdir(parents=True, exist_ok=True)
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    app.mount("/", StaticFiles(directory=SITE_OUTPUT, html=True), name="static")
    yield


app = FastAPI(title="flubpub", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/pages", response_model=PageResponse)
def create_page(body: PageCreate):
    slug = body.slug or slugify(body.title)
    if not slug:
        raise HTTPException(status_code=400, detail="Could not derive slug from title")

    theme = body.theme
    if theme and theme not in available_themes():
        raise HTTPException(status_code=400, detail=f"Unknown theme: {theme}")

    cs = body.color_scheme
    if cs and cs not in available_color_schemes():
        raise HTTPException(status_code=400, detail=f"Unknown color scheme: {cs}")

    # Detect index page. Two seams: a leading <!--FLUBPUB ...--> comment in
    # HTML content, or an `index:` block in markdown frontmatter. Either is
    # authoritative — overrides body.index and forces content_type=index.
    # The triggering block is stripped before storage so it doesn't leak into
    # the rendered page or 11ty's frontmatter parser.
    content = body.content
    content_type = body.content_type
    index_source_format: str | None = None
    parsed_spec: IndexSpec | None = None
    stripped = content
    if content_type == "markdown":
        parsed_spec, stripped = parse_index_spec_from_markdown(content)
        if parsed_spec is not None:
            index_source_format = "markdown"
    if parsed_spec is None:
        parsed_spec, stripped = parse_index_spec_from_html(content)
        if parsed_spec is not None:
            index_source_format = "html"
    index_spec = body.index
    if parsed_spec is not None:
        index_spec = parsed_spec
        content = stripped
        content_type = "index"
    elif index_spec is not None and content_type == "markdown":
        # Index spec arrived via API (e.g. CLI parsed frontmatter and lifted
        # it into a structured field). Promote content_type and treat as a
        # markdown-sourced index.
        content_type = "index"
        index_source_format = "markdown"

    # Markdown-sourced indexes may carry a theme; HTML-sourced indexes do not
    # (the HTML already declares its own styling).
    can_theme = content_type != "index" or index_source_format == "markdown"
    applied_theme = theme if can_theme else None
    applied_cs = cs if can_theme else None

    now = datetime.now(timezone.utc)
    if content_type == "index":
        # Markdown-sourced indexes render through the theme (or 11ty base.njk
        # if no theme); HTML-sourced indexes stay as raw HTML. inject_index_pages
        # then substitutes the list sentinel and JSON marker on top.
        write_ct = "markdown" if index_source_format == "markdown" else "html_raw"
        write_page_file(slug, body.title, content, now.isoformat(),
                        theme=applied_theme, color_scheme=applied_cs,
                        content_type=write_ct)
    else:
        write_page_file(slug, body.title, content, now.isoformat(),
                        applied_theme, applied_cs, content_type=content_type)

    pages = load_pages(DATA_DIR)
    pages = [p for p in pages if p["slug"] != slug]  # replace on re-create
    entry = {
        "title": body.title,
        "slug": slug,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
        **({"theme": applied_theme} if applied_theme else {}),
        **({"color_scheme": applied_cs} if applied_cs else {}),
        **({"content_type": content_type}
           if content_type in ("html_raw", "index") else {}),
        **({"index": index_spec.model_dump()} if index_spec else {}),
        **({"parent": body.parent} if body.parent else {}),
        **({"excerpt": body.excerpt} if body.excerpt else {}),
        **({"tags": body.tags} if body.tags else {}),
        **({"tile": body.tile} if body.tile else {}),
    }
    pages.append(entry)
    save_pages(DATA_DIR, pages)

    rebuild_site(SITE_DIR)
    return PageResponse(**entry, url=f"/{slug}/")


@app.post("/api/assets/{slug}")
async def upload_asset(slug: str, file: UploadFile = File(...)):
    asset_dir = ASSETS_DIR / slug
    asset_dir.mkdir(parents=True, exist_ok=True)
    dest = asset_dir / file.filename
    content = await file.read()
    dest.write_bytes(content)
    rebuild_site(SITE_DIR)
    return {"path": f"/assets/{slug}/{file.filename}"}


@app.get("/api/pages", response_model=list[PageResponse])
def list_pages():
    pages = load_pages(DATA_DIR)
    pages.sort(key=lambda p: p["created_at"], reverse=True)
    return [PageResponse(**p, url=f"/{p['slug']}/") for p in pages]


@app.get("/api/pages/{slug}", response_model=PageDetail)
def get_page(slug: str):
    pages = load_pages(DATA_DIR)
    entry = next((p for p in pages if p["slug"] == slug), None)
    if not entry:
        raise HTTPException(status_code=404, detail="Page not found")

    page_path = PAGES_DIR / f"{slug}.md"
    if not page_path.exists():
        page_path = PAGES_DIR / f"{slug}.html"
    if not page_path.exists():
        raise HTTPException(status_code=404, detail="Page file not found")

    raw = page_path.read_text()
    # Strip YAML frontmatter
    parts = raw.split("---", 2)
    content = parts[2].strip() if len(parts) >= 3 else raw

    ext = page_path.suffix.lstrip(".")
    if entry.get("content_type") == "html_raw":
        content_type = "html_raw"
    else:
        content_type = "markdown" if ext == "md" else ext or "markdown"

    return PageDetail(**entry, url=f"/{slug}/", content=content, content_type=content_type)


@app.put("/api/pages/{slug}", response_model=PageResponse)
def update_page(slug: str, body: PageUpdate):
    pages = load_pages(DATA_DIR)
    entry = next((p for p in pages if p["slug"] == slug), None)
    if not entry:
        raise HTTPException(status_code=404, detail="Page not found")

    page_path = PAGES_DIR / f"{slug}.md"
    if not page_path.exists():
        page_path = PAGES_DIR / f"{slug}.html"
    if not page_path.exists():
        raise HTTPException(status_code=404, detail="Page file not found")

    theme = body.theme if body.theme is not None else entry.get("theme")
    if theme and theme not in available_themes():
        raise HTTPException(status_code=400, detail=f"Unknown theme: {theme}")

    cs = body.color_scheme if body.color_scheme is not None else entry.get("color_scheme")
    if cs and cs not in available_color_schemes():
        raise HTTPException(status_code=400, detail=f"Unknown color scheme: {cs}")

    content_type = body.content_type or entry.get("content_type") or (
        "html_raw" if page_path.suffix == ".html" and not theme else "markdown"
    )

    title = body.title or entry["title"]
    index_spec = body.index
    index_source_format: str | None = None
    if body.content is not None:
        content = body.content
        # Re-parse the index seams on update; in-file content is authoritative.
        parsed_spec: IndexSpec | None = None
        stripped = content
        if content_type == "markdown":
            parsed_spec, stripped = parse_index_spec_from_markdown(content)
            if parsed_spec is not None:
                index_source_format = "markdown"
        if parsed_spec is None:
            parsed_spec, stripped = parse_index_spec_from_html(content)
            if parsed_spec is not None:
                index_source_format = "html"
        if parsed_spec is not None:
            index_spec = parsed_spec
            content = stripped
            content_type = "index"
        elif index_spec is not None and content_type == "markdown":
            # Index spec arrived via API; promote content_type and treat as
            # markdown-sourced index. Mirrors create_page.
            content_type = "index"
            index_source_format = "markdown"
    else:
        raw = page_path.read_text()
        parts = raw.split("---", 2)
        content = parts[2].strip() if len(parts) >= 3 else raw
        if content_type == "index":
            # Preserve the on-disk format (md vs html) when only metadata changes.
            index_source_format = "markdown" if page_path.suffix == ".md" else "html"

    # Markdown-sourced indexes may carry a theme; HTML-sourced indexes do not.
    can_theme = content_type != "index" or index_source_format == "markdown"
    applied_theme = theme if can_theme else None
    applied_cs = cs if can_theme else None

    now = datetime.now(timezone.utc)
    if content_type == "index":
        write_ct = "markdown" if index_source_format == "markdown" else "html_raw"
        write_page_file(slug, title, content, entry["created_at"],
                        theme=applied_theme, color_scheme=applied_cs,
                        content_type=write_ct)
    else:
        write_page_file(slug, title, content, entry["created_at"],
                        applied_theme, applied_cs, content_type=content_type)

    entry["title"] = title
    entry["updated_at"] = now.isoformat()
    if applied_theme:
        entry["theme"] = applied_theme
    elif "theme" in entry:
        del entry["theme"]
    if applied_cs:
        entry["color_scheme"] = applied_cs
    elif "color_scheme" in entry:
        del entry["color_scheme"]
    if content_type in ("html_raw", "index"):
        entry["content_type"] = content_type
    elif "content_type" in entry:
        del entry["content_type"]
    if index_spec is not None:
        entry["index"] = index_spec.model_dump()
    if body.parent is not None:
        if body.parent:
            entry["parent"] = body.parent
        else:
            entry.pop("parent", None)
    if body.excerpt is not None:
        if body.excerpt:
            entry["excerpt"] = body.excerpt
        else:
            entry.pop("excerpt", None)
    if body.tags is not None:
        if body.tags:
            entry["tags"] = body.tags
        else:
            entry.pop("tags", None)
    if body.tile is not None:
        if body.tile:
            entry["tile"] = body.tile
        else:
            entry.pop("tile", None)
    save_pages(DATA_DIR, pages)

    rebuild_site(SITE_DIR)
    return PageResponse(**entry, url=f"/{slug}/")


@app.delete("/api/pages/{slug}")
def delete_page(slug: str):
    md_path = PAGES_DIR / f"{slug}.md"
    html_path = PAGES_DIR / f"{slug}.html"
    if not md_path.exists() and not html_path.exists():
        raise HTTPException(status_code=404, detail="Page not found")
    md_path.unlink(missing_ok=True)
    html_path.unlink(missing_ok=True)

    pages = [p for p in load_pages(DATA_DIR) if p["slug"] != slug]
    save_pages(DATA_DIR, pages)

    rebuild_site(SITE_DIR)
    return {"deleted": slug}


class IndexBody(BaseModel):
    """Payload for `/api/index`.

    `content` is HTML when content_type='html_raw' (the historic shape, raw
    HTML with the `<script id="flubpub-pages">` marker baked in) or markdown
    when content_type='markdown' (rendered server-side, optionally wrapped
    in a flubpub theme). `index` carries an IndexSpec the post-build
    injection step uses to filter/sort/group the page list. The remaining
    fields tune how the markdown shell or themed page is rendered."""
    content: str
    content_type: str = "html_raw"
    title: str = "Home"
    theme: str | None = None
    color_scheme: str | None = None
    style_css: str | None = None
    index: IndexSpec | None = None


_MD_ROOT_SHELL = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
{cs_block}
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
    Helvetica, Arial, sans-serif; max-width: 720px; margin: 0 auto;
    padding: 1.5rem 1rem 3rem; line-height: 1.6;
    color: var(--fg, #222); background: var(--bg, #fff); }}
  a {{ color: var(--link, #0055cc); }}
  a:visited {{ color: var(--link-visited, #551a8b); }}
  img {{ max-width: 100%; height: auto; }}
  h1, h2, h3 {{ line-height: 1.25; color: var(--heading, inherit); }}
  ul.flubpub-pages {{ list-style: none; padding: 0; }}
  ul.flubpub-pages li {{ margin: 0.6rem 0; }}
  .flubpub-date {{ color: var(--muted, #777); }}
  .flubpub-excerpt {{ color: var(--muted, #555); font-size: 0.95em; margin-top: 0.15rem; }}
  code, pre {{ background: var(--code-bg, #f4f4f4); color: var(--code-fg, inherit); }}
  table {{ border-collapse: collapse; }}
  table td, table th {{ padding: 0.25rem 0.75rem 0.25rem 0; vertical-align: top; }}
{extra_css}
</style>
</head>
<body>
<main>
{body}
</main>
<script type="application/json" id="flubpub-pages">[]</script>
</body>
</html>
"""


def _render_root_markdown(body: IndexBody) -> str:
    """Markdown → finished HTML for the root index. When a theme is given,
    reuse the per-page theme renderer (so the site's theme catalogue applies
    uniformly to root); otherwise fall back to the standalone shell with
    optional color-scheme CSS variables and operator-supplied extra CSS."""
    rendered_body = _render_markdown_to_html(body.content)

    if body.theme:
        if body.theme not in available_themes():
            raise HTTPException(status_code=400, detail=f"Unknown theme: {body.theme}")
        cs = body.color_scheme
        if cs and cs not in available_color_schemes():
            raise HTTPException(status_code=400, detail=f"Unknown color scheme: {cs}")
        # Themed pages expect HTML content; wrap the rendered markdown in
        # the same .markdown-content div used elsewhere so the theme's CSS
        # selectors match.
        wrapped = f'<div class="markdown-content">{rendered_body}</div>'
        themed = render_themed_page(
            theme=body.theme,
            slug="",
            title=body.title,
            content=wrapped,
            date="",
            color_scheme=cs,
        )
        # The themed templates don't carry a JSON marker, so add one before
        # </body> so inject_index_pages can still publish the payload.
        marker = f'\n<script type="application/json" id="{INDEX_PAGES_MARKER_ID}">[]</script>\n'
        if "</body>" in themed:
            themed = themed.replace("</body>", marker + "</body>", 1)
        else:
            themed += marker
        return themed

    # No theme: use the inline shell. color_scheme still injects CSS vars.
    cs_block = ""
    if body.color_scheme:
        if body.color_scheme not in available_color_schemes():
            raise HTTPException(
                status_code=400, detail=f"Unknown color scheme: {body.color_scheme}"
            )
        cs_block = color_scheme_css(body.color_scheme)
    extra_css = body.style_css or ""
    return _MD_ROOT_SHELL.format(
        title=body.title,
        cs_block=cs_block,
        extra_css=extra_css,
        body=rendered_body,
    )


@app.post("/api/index")
def set_custom_index(body: IndexBody):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if body.content_type == "markdown":
        full = _render_root_markdown(body)
        CUSTOM_INDEX_SRC.write_text(full)
    else:
        CUSTOM_INDEX_SRC.write_text(body.content)

    if body.index is not None:
        CUSTOM_INDEX_SPEC.write_text(
            json.dumps(body.index.model_dump(), indent=2, default=str)
        )
    else:
        CUSTOM_INDEX_SPEC.unlink(missing_ok=True)

    rebuild_site(SITE_DIR)
    return {"status": "ok", "marker": INDEX_PAGES_MARKER_ID}


@app.delete("/api/index")
def clear_custom_index():
    CUSTOM_INDEX_SRC.unlink(missing_ok=True)
    CUSTOM_INDEX_SPEC.unlink(missing_ok=True)
    rebuild_site(SITE_DIR)
    return {"status": "ok"}


@app.get("/api/themes")
def list_themes():
    return available_themes()


@app.get("/api/color-schemes")
def list_color_schemes():
    return available_color_schemes()


if __name__ == "__main__":
    uvicorn.run("flubpub.server:app", host="0.0.0.0", port=8000, reload=True)
