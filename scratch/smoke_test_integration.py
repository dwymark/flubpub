"""Integration smoke test: stand up a temporary site dir, push an index
page through the server's create_page handler, run rebuild, and verify the
marker is substituted in _site/<slug>/index.html.

Run with: uv run python3 scratch/smoke_test_integration.py
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def setup_workspace() -> Path:
    """Build a fresh temp workspace mirroring flubpub's data/site layout."""
    work = Path(tempfile.mkdtemp(prefix="flubpub-smoke-"))
    (work / "data").mkdir()
    (work / "site" / "src" / "pages").mkdir(parents=True)
    (work / "site" / "src" / "assets").mkdir()
    # Borrow the project's 11ty config + index template + base layout
    repo = Path.cwd()
    shutil.copy(repo / "site" / "eleventy.config.js", work / "site" / "eleventy.config.js")
    shutil.copytree(repo / "site" / "src" / "_includes", work / "site" / "src" / "_includes")
    shutil.copy(repo / "site" / "src" / "index.njk", work / "site" / "src" / "index.njk")
    shutil.copy(repo / "site" / "src" / "pages" / "pages.json",
                work / "site" / "src" / "pages" / "pages.json")
    # Need a package.json so npx finds @11ty/eleventy. Copy from repo if exists.
    pkg = repo / "site" / "package.json"
    if pkg.exists():
        shutil.copy(pkg, work / "site" / "package.json")
    nm = repo / "site" / "node_modules"
    if nm.exists():
        # Symlink to avoid huge copy
        (work / "site" / "node_modules").symlink_to(nm)
    return work


def render_template(template: str, slug: str, work: Path) -> str:
    """Use the CLI's new-index command to render a template into a working file."""
    out = work / f"{slug}.html"
    repo = Path.cwd()
    subprocess.run(
        [
            "uv", "run", "flubpub", "new-index",
            "--template", template,
            "--output", str(out),
            "--copy-assets",
        ],
        cwd=repo,
        check=True,
    )
    body = out.read_text()
    # Prepend a FLUBPUB comment so the server classifies as content_type=index
    flubpub = f"""<!--FLUBPUB
content_type: index
index:
  template: {template}
  sort: {{ by: created_at, order: desc }}
  limit: 10
-->
"""
    return flubpub + body


def push_via_handler(work: Path, slug: str, title: str, html: str) -> None:
    """Invoke server.create_page directly with the right env vars set."""
    os.environ["FLUBPUB_DATA_DIR"] = str(work / "data")
    os.environ["FLUBPUB_SITE_DIR"] = str(work / "site")
    # Force the server module to re-resolve those paths.
    if "flubpub.server" in sys.modules:
        del sys.modules["flubpub.server"]
    from flubpub.server import create_page
    from flubpub.models import PageCreate
    body = PageCreate(title=title, slug=slug, content=html, content_type="html_raw")
    resp = create_page(body)
    print(f"create_page → {resp.url}")


def verify(work: Path, slug: str) -> None:
    """Inspect _site/<slug>/index.html to confirm marker substitution worked."""
    out = work / "site" / "_site" / slug / "index.html"
    if not out.exists():
        print(f"FAIL — {out} does not exist")
        return
    content = out.read_text()
    # Look for the marker, find its substituted JSON
    import re
    m = re.search(r'<script[^>]*id="flubpub-pages"[^>]*>(.*?)</script>', content, re.DOTALL)
    if not m:
        print(f"FAIL — marker not found in {out}")
        return
    inner = m.group(1).strip()
    try:
        parsed = json.loads(inner)
    except json.JSONDecodeError as e:
        print(f"FAIL — marker contents not valid JSON: {e}")
        print(f"contents: {inner[:200]}")
        return
    print(f"PASS — marker substituted with {len(parsed)} page(s)")
    if parsed:
        print(f"  first entry: title={parsed[0].get('title')!r} url={parsed[0].get('url')!r}")
    print(f"\nOutput at: {out}")


def main():
    # Force unbuffered output so progress is visible
    sys.stdout.reconfigure(line_buffering=True)
    work = setup_workspace()
    print(f"workspace: {work}\n", flush=True)

    # Push a few "regular" markdown pages that the index will list
    os.environ["FLUBPUB_DATA_DIR"] = str(work / "data")
    os.environ["FLUBPUB_SITE_DIR"] = str(work / "site")
    if "flubpub.server" in sys.modules:
        del sys.modules["flubpub.server"]
    from flubpub.server import create_page
    from flubpub.models import PageCreate

    create_page(PageCreate(title="First Essay", slug="first-essay",
                           content="The opening lines of the first essay.",
                           content_type="markdown"))
    create_page(PageCreate(title="Second Essay", slug="second-essay",
                           content="A continuation, with thoughts about geometry.",
                           content_type="markdown"))
    create_page(PageCreate(title="Third Sketch", slug="third-sketch",
                           content="Some marginalia.",
                           content_type="markdown"))

    # Now push an index page for each template
    templates = ["quiet-list", "timeline", "voronoi-map", "constellation",
                 "topographic", "mindmap", "marginalia", "gallery"]
    for tmpl in templates:
        slug = f"{tmpl}-index"
        title = f"{tmpl} index"
        html = render_template(tmpl, slug, work)
        push_via_handler(work, slug, title, html)
        verify(work, slug)
        print()


if __name__ == "__main__":
    main()
