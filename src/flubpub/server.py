import json
import logging
import os
import re
import shutil
import subprocess
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

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
# Timestamps in pages.json are stored as UTC ISO strings; display lists
# render them in this timezone. Default UTC keeps behavior unchanged for
# installs that don't set it. Per-instance via systemd's instance.env.
def _resolve_display_tz() -> ZoneInfo:
    name = os.environ.get("FLUBPUB_DISPLAY_TZ", "UTC")
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        logger.warning("Unknown FLUBPUB_DISPLAY_TZ=%r, falling back to UTC", name)
        return ZoneInfo("UTC")

DISPLAY_TZ = _resolve_display_tz()

# The site front page (URL "/") is just a page-type index that lives at this
# reserved slug. There is exactly one index model — see inject_index_pages and
# set_custom_index. (Legacy paths data/custom_index.html + custom_index_spec.json
# are swept on the next set-index/unset-index; see _sweep_legacy_root_index.)
ROOT_INDEX_SLUG = "index"
_LEGACY_ROOT_HTML = DATA_DIR / "custom_index.html"
_LEGACY_ROOT_SPEC = DATA_DIR / "custom_index_spec.json"
INDEX_PAGES_MARKER_ID = "flubpub-pages"

# Sentinel substituted with a server-rendered HTML <ul> of the index payload.
# Survives markdown-it as either a bare comment or wrapped in <p>…</p>.
LIST_SENTINEL = "<!--FLUBPUB-LIST-->"

# Lift a description from raw HTML's <meta name="description" content="..."> so
# index lists can show a per-page subtitle without a separate CLI flag.
_META_DESCRIPTION_RE = re.compile(
    r'<meta\b[^>]*\bname\s*=\s*["\']description["\'][^>]*\bcontent\s*=\s*["\']([^"\']*)["\']',
    re.IGNORECASE,
)


def _extract_meta_description(content: str) -> str | None:
    m = _META_DESCRIPTION_RE.search(content)
    return m.group(1).strip() if m and m.group(1).strip() else None

_LIST_SENTINEL_RE = re.compile(
    r"(<p>\s*)?" + re.escape(LIST_SENTINEL) + r"(\s*</p>)?",
    re.IGNORECASE,
)


def _render_pages_list_html(payload: list[dict], show_dates: bool = True) -> str:
    """Render an index payload as a simple <ul>. Handles both flat lists and
    grouped {label, pages} sections. `show_dates` suppresses the per-entry
    timestamp so landing-page indexes can let the artifacts speak for
    themselves."""
    if not payload:
        return '<p class="flubpub-empty">No pages yet.</p>'

    def _date(p: dict) -> str:
        v = p.get("created_at") or ""
        if not isinstance(v, str) or len(v) < 10:
            return ""
        try:
            dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError:
            return v[:10]
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(DISPLAY_TZ).strftime("%Y-%m-%d")

    def _li(p: dict) -> str:
        title = p.get("title") or p.get("slug") or "(untitled)"
        url = p.get("url") or f"/{p.get('slug', '')}/"
        date = _date(p) if show_dates else ""
        excerpt = p.get("excerpt")
        description = p.get("description")
        bits = [f'<a href="{url}">{title}</a>']
        if date:
            bits.append(f' <small class="flubpub-date">{date}</small>')
        if excerpt:
            bits.append(f'<div class="flubpub-excerpt">{excerpt}</div>')
        if description:
            bits.append(f'<div class="flubpub-description">{description}</div>')
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


def _substitute_list_sentinel(html: str, payload: list[dict], show_dates: bool = True) -> str:
    """Replace the first occurrence of LIST_SENTINEL (and any wrapping <p>)
    with a server-rendered list. Returns html unchanged if no sentinel."""
    if LIST_SENTINEL not in html:
        return html
    rendered = _render_pages_list_html(payload, show_dates=show_dates)
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
    inject_index_pages()


def _inject_marker(html: str, spec: IndexSpec, all_pages: list[dict], self_slug: str) -> str:
    """Substitute both index seams in `html` with the personalized payload for
    `spec`: the JSON `<script id="flubpub-pages">` marker (used by template-
    driven indexes), and the `<!--FLUBPUB-LIST-->` sentinel (used by prose-
    headed markdown indexes for a server-rendered <ul>). Either or both may
    be absent — each substitution is a no-op when its target isn't found."""
    payload = build_index_payload(spec, all_pages, self_slug)
    payload_json = json.dumps(payload, indent=2, default=str)
    html = substitute_pages_marker(html, payload_json)
    html = _substitute_list_sentinel(html, payload, show_dates=spec.show_dates)
    return html


def inject_index_pages() -> None:
    """For every index page (content_type=='index' in pages.json), substitute
    the #flubpub-pages marker and the <!--FLUBPUB-LIST--> sentinel with that
    page's personalized payload and write the result back to _site.

    One model, one loop. The site front page is the entry at ROOT_INDEX_SLUG;
    its only specialness is mechanical — its URL is "/", so its injected output
    lands at _site/index.html (overwriting 11ty's src/index.njk build) instead
    of _site/<slug>/index.html. 11ty actually builds the root index at
    _site/pages/index.html (because fileSlug for src/pages/index.html resolves
    to the parent dir), and the duplicate there is removed after injection."""
    all_pages = load_pages(DATA_DIR)

    for entry in all_pages:
        if entry.get("content_type") != "index":
            continue
        slug = entry["slug"]
        # 11ty's fileSlug for src/pages/index.html resolves to the parent
        # dir name ("pages"), so the root-index build lands at
        # _site/pages/index.html, not _site/index/index.html.
        if slug == ROOT_INDEX_SLUG:
            built = SITE_OUTPUT / "pages" / "index.html"
        else:
            built = SITE_OUTPUT / slug / "index.html"
        if not built.exists():
            continue
        try:
            spec = IndexSpec(**(entry.get("index") or {}))
        except Exception as e:
            logger.warning("Bad index spec for %s: %s", slug, e)
            continue
        html = _inject_marker(built.read_text(), spec, all_pages, self_slug=slug)
        if slug == ROOT_INDEX_SLUG:
            SITE_OUTPUT.mkdir(parents=True, exist_ok=True)
            (SITE_OUTPUT / "index.html").write_text(html)
            (SITE_OUTPUT / "pages" / "index.html").unlink(missing_ok=True)
        else:
            built.write_text(html)


def _sweep_legacy_root_index() -> None:
    """One-shot reclamation: the pre-unification root index stored a rendered
    blob at data/custom_index.html plus a sidecar spec. Those are dead under
    the unified model; drop them whenever the root index is (re)written or
    cleared so no stale artifact lingers on an upgraded install."""
    _LEGACY_ROOT_HTML.unlink(missing_ok=True)
    _LEGACY_ROOT_SPEC.unlink(missing_ok=True)


def resolve_index(
    content: str,
    content_type: str,
    body_index: IndexSpec | None,
    *,
    force_index: bool = False,
) -> tuple[str, str, IndexSpec | None, str | None]:
    """Single source of truth for "is this an index page, and in what form?".

    Detection seams, in priority order:
      1. a leading <!--FLUBPUB ...--> comment (HTML) or an `index:` block in
         markdown frontmatter — in-file content is authoritative and the
         triggering block is stripped so it can't leak into the rendered page
         or 11ty's frontmatter parser;
      2. an IndexSpec that arrived structurally via the API (e.g. the CLI
         lifted `.md` frontmatter into a field) on markdown content;
      3. `force_index` — the caller (the root /api/index endpoint) declares
         this is an index regardless of content shape; an empty spec defaults
         to "all pages, newest first".

    Returns (content, content_type, index_spec, index_source_format).
    `index_source_format` is "markdown" | "html" | None and decides whether a
    theme may be applied (markdown-sourced indexes may be themed; HTML-sourced
    ones already declare their own styling).

    create_page and update_page both call this; keep it the only place the
    promotion rules live."""
    index_source_format: str | None = None
    parsed_spec: IndexSpec | None = None
    if content_type == "markdown":
        parsed_spec, stripped = parse_index_spec_from_markdown(content)
        if parsed_spec is not None:
            index_source_format = "markdown"
    if parsed_spec is None:
        parsed_spec, stripped = parse_index_spec_from_html(content)
        if parsed_spec is not None:
            index_source_format = "html"

    index_spec = body_index
    if parsed_spec is not None:
        return stripped, "index", parsed_spec, index_source_format
    if index_spec is not None and content_type == "markdown":
        return content, "index", index_spec, "markdown"
    if force_index:
        fmt = "markdown" if content_type == "markdown" else "html"
        return content, "index", index_spec or IndexSpec(), fmt
    return content, content_type, index_spec, None


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


def _create_or_replace_page(
    *, slug: str, title: str, content: str, content_type: str,
    index_spec: IndexSpec | None, index_source_format: str | None,
    theme: str | None, color_scheme: str | None,
    parent: str | None, excerpt: str | None,
    description: str | None,
    tags: list[str], tile: dict | None,
) -> dict:
    """Write the page file + (re)create the pages.json entry + rebuild. The
    single create/replace path; create_page and the root /api/index endpoint
    both funnel through here so there is one persistence model, not two."""
    # Markdown-sourced indexes may carry a theme; HTML-sourced indexes do not
    # (the HTML already declares its own styling).
    can_theme = content_type != "index" or index_source_format == "markdown"
    applied_theme = theme if can_theme else None
    applied_cs = color_scheme if can_theme else None

    now = datetime.now(timezone.utc)
    if content_type == "index":
        # Markdown-sourced indexes render through the theme (or 11ty base.njk
        # if no theme); HTML-sourced indexes stay as raw HTML. inject_index_pages
        # then substitutes the list sentinel and JSON marker on top.
        write_ct = "markdown" if index_source_format == "markdown" else "html_raw"
        write_page_file(slug, title, content, now.isoformat(),
                        theme=applied_theme, color_scheme=applied_cs,
                        content_type=write_ct)
    else:
        write_page_file(slug, title, content, now.isoformat(),
                        applied_theme, applied_cs, content_type=content_type)

    # Lift a meta description out of raw HTML when the caller didn't pass one
    # explicitly; markdown pages get this through CLI frontmatter merging.
    if not description and content_type in ("html_raw", "index"):
        description = _extract_meta_description(content)

    pages = load_pages(DATA_DIR)
    pages = [p for p in pages if p["slug"] != slug]  # replace on re-create
    entry = {
        "title": title,
        "slug": slug,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
        **({"theme": applied_theme} if applied_theme else {}),
        **({"color_scheme": applied_cs} if applied_cs else {}),
        **({"content_type": content_type}
           if content_type in ("html_raw", "index") else {}),
        **({"index": index_spec.model_dump()} if index_spec else {}),
        **({"parent": parent} if parent else {}),
        **({"excerpt": excerpt} if excerpt else {}),
        **({"description": description} if description else {}),
        **({"tags": tags} if tags else {}),
        **({"tile": tile} if tile else {}),
    }
    pages.append(entry)
    save_pages(DATA_DIR, pages)

    rebuild_site(SITE_DIR)
    return entry


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

    content, content_type, index_spec, index_source_format = resolve_index(
        body.content, body.content_type, body.index
    )

    entry = _create_or_replace_page(
        slug=slug, title=body.title, content=content, content_type=content_type,
        index_spec=index_spec, index_source_format=index_source_format,
        theme=theme, color_scheme=cs,
        parent=body.parent, excerpt=body.excerpt,
        description=body.description,
        tags=body.tags, tile=body.tile,
    )
    return PageResponse(**entry, url=f"/{slug}/")


# The slug grammar used everywhere else (slugify()): lowercase alnum + hyphen.
# Anchored, so no "/", ".", or ".." can sneak through into a path segment.
_SAFE_SLUG_RE = re.compile(r"\A[a-z0-9-]+\Z")


@app.post("/api/assets/{slug}")
async def upload_asset(slug: str, file: UploadFile = File(...)):
    # Defense in depth: even though nginx no longer proxies /api/ publicly and
    # uvicorn binds 127.0.0.1, never let a client-controlled slug or filename
    # escape the assets tree. Both are reduced to a single safe path segment.
    if not _SAFE_SLUG_RE.match(slug):
        raise HTTPException(status_code=400, detail=f"Invalid asset slug: {slug!r}")
    safe_name = Path(file.filename or "").name
    if not safe_name or safe_name in (".", ".."):
        raise HTTPException(status_code=400, detail="Invalid asset filename")
    asset_dir = ASSETS_DIR / slug
    asset_dir.mkdir(parents=True, exist_ok=True)
    dest = asset_dir / safe_name
    content = await file.read()
    dest.write_bytes(content)
    rebuild_site(SITE_DIR)
    return {"path": f"/assets/{slug}/{safe_name}"}


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
        # Re-resolve the index seams on update; in-file content is authoritative.
        content, content_type, index_spec, index_source_format = resolve_index(
            body.content, content_type, body.index
        )
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
    # Description handling: explicit body.description wins; on a content
    # update without an explicit description, re-lift from HTML <meta>.
    if body.description is not None:
        if body.description:
            entry["description"] = body.description
        else:
            entry.pop("description", None)
    elif body.content is not None and content_type in ("html_raw", "index"):
        lifted = _extract_meta_description(content)
        if lifted:
            entry["description"] = lifted
        else:
            entry.pop("description", None)
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
    """Payload for `/api/index` — the site front page.

    `/api/index` is sugar: the front page is just the page-type index at
    ROOT_INDEX_SLUG, and this endpoint funnels into the same create/replace
    path every other index uses. `content` is markdown (content_type=
    'markdown', themed via `theme` or rendered through 11ty base.njk) or raw
    HTML (content_type='html_raw', e.g. a rendered gallery template carrying
    the `<script id="flubpub-pages">` marker). `index` is the IndexSpec the
    post-build injection step filters/sorts/groups the page list with; an
    absent/empty spec defaults to all pages, newest first."""
    content: str
    content_type: str = "html_raw"
    title: str = "Home"
    theme: str | None = None
    color_scheme: str | None = None
    index: IndexSpec | None = None


@app.post("/api/index")
def set_custom_index(body: IndexBody):
    """Install/replace the site front page. Thin adaptor over the unified
    page-type index model: classify (force_index — this endpoint is by
    definition the root index), then create/replace the entry at
    ROOT_INDEX_SLUG. inject_index_pages routes its output to _site/index.html."""
    if body.theme and body.theme not in available_themes():
        raise HTTPException(status_code=400, detail=f"Unknown theme: {body.theme}")
    if body.color_scheme and body.color_scheme not in available_color_schemes():
        raise HTTPException(
            status_code=400, detail=f"Unknown color scheme: {body.color_scheme}"
        )

    content, content_type, index_spec, index_source_format = resolve_index(
        body.content, body.content_type, body.index, force_index=True
    )
    _create_or_replace_page(
        slug=ROOT_INDEX_SLUG, title=body.title, content=content,
        content_type=content_type, index_spec=index_spec,
        index_source_format=index_source_format,
        theme=body.theme, color_scheme=body.color_scheme,
        parent=None, excerpt=None, description=None, tags=[], tile=None,
    )
    _sweep_legacy_root_index()
    return {"status": "ok", "marker": INDEX_PAGES_MARKER_ID}


@app.delete("/api/index")
def clear_custom_index():
    """Remove the custom front page — delete the ROOT_INDEX_SLUG entry so
    11ty's default src/index.njk build wins again."""
    (PAGES_DIR / f"{ROOT_INDEX_SLUG}.md").unlink(missing_ok=True)
    (PAGES_DIR / f"{ROOT_INDEX_SLUG}.html").unlink(missing_ok=True)
    pages = [p for p in load_pages(DATA_DIR) if p["slug"] != ROOT_INDEX_SLUG]
    save_pages(DATA_DIR, pages)
    _sweep_legacy_root_index()
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
