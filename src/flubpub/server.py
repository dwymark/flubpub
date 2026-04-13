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

from flubpub.models import PageCreate, PageDetail, PageResponse, PageUpdate

logger = logging.getLogger(__name__)

DATA_DIR = Path(os.environ.get("FLUBPUB_DATA_DIR", "./data"))
SITE_DIR = Path(os.environ.get("FLUBPUB_SITE_DIR", "./site"))
PAGES_DIR = SITE_DIR / "src" / "pages"
PAGES_JSON = DATA_DIR / "pages.json"
SITE_OUTPUT = SITE_DIR / "_site"
ASSETS_DIR = SITE_DIR / "src" / "assets"
THEMES_DIR = Path(__file__).parent / "themes"

jinja_env = Environment(loader=PackageLoader("flubpub", "themes"))


def available_themes() -> list[str]:
    return [f.stem for f in THEMES_DIR.glob("*.html")]


def render_themed_page(theme: str, slug: str, title: str, content: str, date: str) -> str:
    template = jinja_env.get_template(f"{theme}.html")
    return template.render(title=title, content=content, date=date, slug=slug)


def write_page_file(slug: str, title: str, content: str, date: str, theme: str | None) -> None:
    """Write the page file (.html for themed, .md for unthemed). Cleans up the other format."""
    old_md, old_html = PAGES_DIR / f"{slug}.md", PAGES_DIR / f"{slug}.html"
    if theme:
        rendered = render_themed_page(theme, slug, title, content, date)
        fm = f'---\ntitle: "{title}"\ndate: "{date}"\nlayout: false\n---\n{rendered}\n'
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

    now = datetime.now(timezone.utc)
    content = body.content
    if theme and body.content_type == "markdown":
        content = f'<div class="markdown-content">{content}</div>'
    write_page_file(slug, body.title, content, now.isoformat(), theme)

    pages = load_pages(DATA_DIR)
    pages = [p for p in pages if p["slug"] != slug]  # replace on re-create
    entry = {
        "title": body.title,
        "slug": slug,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
        **({"theme": theme} if theme else {}),
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

    title = body.title or entry["title"]
    if body.content is not None:
        content = body.content
        if theme and body.content_type == "markdown":
            content = f'<div class="markdown-content">{content}</div>'
    else:
        raw = page_path.read_text()
        parts = raw.split("---", 2)
        content = parts[2].strip() if len(parts) >= 3 else raw

    now = datetime.now(timezone.utc)
    write_page_file(slug, title, content, entry["created_at"], theme)

    entry["title"] = title
    entry["updated_at"] = now.isoformat()
    if theme:
        entry["theme"] = theme
    elif "theme" in entry:
        del entry["theme"]
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


@app.get("/api/themes")
def list_themes():
    return available_themes()


if __name__ == "__main__":
    uvicorn.run("flubpub.server:app", host="0.0.0.0", port=8000, reload=True)
