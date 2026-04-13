import json
import logging
import os
import re
import subprocess
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

from flubpub.models import PageCreate, PageDetail, PageResponse, PageUpdate

logger = logging.getLogger(__name__)

DATA_DIR = Path(os.environ.get("FLUBPUB_DATA_DIR", "./data"))
SITE_DIR = Path(os.environ.get("FLUBPUB_SITE_DIR", "./site"))
PAGES_DIR = SITE_DIR / "src" / "pages"
PAGES_JSON = DATA_DIR / "pages.json"
SITE_OUTPUT = SITE_DIR / "_site"


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

    now = datetime.now(timezone.utc)
    md_path = PAGES_DIR / f"{slug}.md"
    frontmatter = f'---\ntitle: "{body.title}"\ndate: "{now.isoformat()}"\n---\n{body.content}\n'
    md_path.write_text(frontmatter)

    pages = load_pages(DATA_DIR)
    pages = [p for p in pages if p["slug"] != slug]  # replace on re-create
    entry = {
        "title": body.title,
        "slug": slug,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }
    pages.append(entry)
    save_pages(DATA_DIR, pages)

    rebuild_site(SITE_DIR)
    return PageResponse(**entry, url=f"/{slug}/")


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

    md_path = PAGES_DIR / f"{slug}.md"
    if not md_path.exists():
        raise HTTPException(status_code=404, detail="Page file not found")

    raw = md_path.read_text()
    # Strip YAML frontmatter
    parts = raw.split("---", 2)
    content = parts[2].strip() if len(parts) >= 3 else raw

    ext = md_path.suffix.lstrip(".")
    content_type = "markdown" if ext == "md" else ext or "markdown"

    return PageDetail(**entry, url=f"/{slug}/", content=content, content_type=content_type)


@app.put("/api/pages/{slug}", response_model=PageResponse)
def update_page(slug: str, body: PageUpdate):
    pages = load_pages(DATA_DIR)
    entry = next((p for p in pages if p["slug"] == slug), None)
    if not entry:
        raise HTTPException(status_code=404, detail="Page not found")

    md_path = PAGES_DIR / f"{slug}.md"
    if not md_path.exists():
        raise HTTPException(status_code=404, detail="Page file not found")

    title = body.title or entry["title"]
    if body.content is not None:
        content = body.content
    else:
        raw = md_path.read_text()
        parts = raw.split("---", 2)
        content = parts[2].strip() if len(parts) >= 3 else raw

    now = datetime.now(timezone.utc)
    frontmatter = f'---\ntitle: "{title}"\ndate: "{entry["created_at"]}"\n---\n{content}\n'
    md_path.write_text(frontmatter)

    entry["title"] = title
    entry["updated_at"] = now.isoformat()
    save_pages(DATA_DIR, pages)

    rebuild_site(SITE_DIR)
    return PageResponse(**entry, url=f"/{slug}/")


@app.delete("/api/pages/{slug}")
def delete_page(slug: str):
    md_path = PAGES_DIR / f"{slug}.md"
    if not md_path.exists():
        raise HTTPException(status_code=404, detail="Page not found")
    md_path.unlink()

    pages = [p for p in load_pages(DATA_DIR) if p["slug"] != slug]
    save_pages(DATA_DIR, pages)

    rebuild_site(SITE_DIR)
    return {"deleted": slug}


if __name__ == "__main__":
    uvicorn.run("flubpub.server:app", host="0.0.0.0", port=8000, reload=True)
