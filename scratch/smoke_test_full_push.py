"""End-to-end test that mimics the actual CLI push flow:

  1. Scaffold an index page from a template via `new-index --copy-assets`.
  2. Prepend a FLUBPUB comment so the server classifies it as an index.
  3. Resolve local refs (script.js, index.css, etc.) via collect_all_refs.
  4. Copy each asset into site/src/assets/<slug>/  (mimics POST /api/assets).
  5. Rewrite the HTML's local refs via rewrite_refs.
  6. Pass the rewritten HTML to server.create_page.
  7. Verify _site/<slug>/index.html and that referenced assets actually exist.

After this, http.server in _site/ should serve every template correctly.

Run with: PYTHONUNBUFFERED=1 uv run python3 scratch/smoke_test_full_push.py
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def setup_workspace() -> Path:
    work = Path(tempfile.mkdtemp(prefix="flubpub-full-"))
    (work / "data").mkdir()
    (work / "site" / "src" / "pages").mkdir(parents=True)
    (work / "site" / "src" / "assets").mkdir()
    repo = Path.cwd()
    shutil.copy(repo / "site" / "eleventy.config.js", work / "site" / "eleventy.config.js")
    shutil.copytree(repo / "site" / "src" / "_includes", work / "site" / "src" / "_includes")
    shutil.copy(repo / "site" / "src" / "index.njk", work / "site" / "src" / "index.njk")
    shutil.copy(repo / "site" / "src" / "pages" / "pages.json",
                work / "site" / "src" / "pages" / "pages.json")
    pkg = repo / "site" / "package.json"
    if pkg.exists():
        shutil.copy(pkg, work / "site" / "package.json")
    nm = repo / "site" / "node_modules"
    if nm.exists():
        (work / "site" / "node_modules").symlink_to(nm)
    return work


FLUBPUB_HEADER = """<!--FLUBPUB
content_type: index
index:
  template: {template}
  sort: {{ by: created_at, order: desc }}
  limit: 10
-->
"""


def scaffold(template: str, slug: str, work: Path) -> Path:
    """Run `flubpub new-index --copy-assets` to drop a working file + assets."""
    scratch = work / "scratch"
    scratch.mkdir(exist_ok=True)
    out = scratch / f"{slug}.html"
    subprocess.run(
        ["uv", "run", "flubpub", "new-index",
         "--template", template,
         "--output", str(out),
         "--copy-assets"],
        cwd=Path.cwd(), check=True,
    )
    # Prepend FLUBPUB comment in-place
    body = out.read_text()
    out.write_text(FLUBPUB_HEADER.format(template=template) + body)
    return out


def push_full(work: Path, file_path: Path, slug: str, title: str) -> None:
    """Mimic the CLI push's asset+page flow without HTTP."""
    os.environ["FLUBPUB_DATA_DIR"] = str(work / "data")
    os.environ["FLUBPUB_SITE_DIR"] = str(work / "site")
    if "flubpub.server" in sys.modules:
        del sys.modules["flubpub.server"]
    from flubpub.server import create_page, ASSETS_DIR
    from flubpub.cli import collect_all_refs, rewrite_refs
    from flubpub.models import PageCreate

    content = file_path.read_text()
    assets, sub_pages = collect_all_refs(file_path)

    # Mimic POST /api/assets/<slug>: copy each file into site/src/assets/<slug>/
    asset_dir = ASSETS_DIR / slug
    asset_dir.mkdir(parents=True, exist_ok=True)
    for a in assets:
        shutil.copy(a, asset_dir / a.name)

    # Rewrite refs in the HTML so they point at /assets/<slug>/<name>
    if assets:
        content = rewrite_refs(content, slug, assets, [], mode="html")

    body = PageCreate(title=title, slug=slug, content=content, content_type="html_raw")
    resp = create_page(body)
    print(f"  pushed → {resp.url} ({len(assets)} asset(s))")


def verify(work: Path, slug: str) -> bool:
    out = work / "site" / "_site" / slug / "index.html"
    ok = True
    if not out.exists():
        print(f"  FAIL — {out} does not exist"); return False
    content = out.read_text()
    m = re.search(r'<script[^>]*id="flubpub-pages"[^>]*>(.*?)</script>', content, re.DOTALL)
    if not m:
        print("  FAIL — marker not found"); return False
    parsed = json.loads(m.group(1).strip())
    print(f"  marker has {len(parsed)} page(s)")

    # Verify every <script src=...> and <link href=...> in the rendered HTML
    # actually resolves to a file in _site/.
    site_root = work / "site" / "_site"
    refs = re.findall(r'(?:src|href)\s*=\s*"(/[^"]+)"', content)
    missing = []
    for ref in refs:
        if ref.startswith("/"):
            target = site_root / ref.lstrip("/")
            if target.is_file():
                continue
            # Many refs end in /, meaning a directory's index.html
            if ref.endswith("/") and (target / "index.html").is_file():
                continue
            missing.append(ref)
    if missing:
        ok = False
        print(f"  FAIL — {len(missing)} unresolved local ref(s):")
        for r in missing[:5]:
            print(f"     {r}")
    else:
        print(f"  PASS — all local refs resolve")
    return ok


def main():
    sys.stdout.reconfigure(line_buffering=True)
    work = setup_workspace()
    print(f"workspace: {work}\n", flush=True)

    os.environ["FLUBPUB_DATA_DIR"] = str(work / "data")
    os.environ["FLUBPUB_SITE_DIR"] = str(work / "site")
    if "flubpub.server" in sys.modules:
        del sys.modules["flubpub.server"]
    from flubpub.server import create_page
    from flubpub.models import PageCreate

    # Seed with mock essays. Rich metadata so each template has signal to show.
    # Dates are spread across two years; tags + accents vary; some posts have
    # parents so the mindmap has structure; excerpts populate marginalia.
    from datetime import datetime, timedelta, timezone
    seeds = [
        dict(slug="fano-plane", title="The Fano Plane",
             excerpt="Seven points, seven lines, and the smallest projective plane. A picture you can almost draw.",
             tags=["math", "geometry"], tile={"accent": "plum"},
             days_ago=2),
        dict(slug="voronoi-cells", title="Voronoi as Cells",
             excerpt="Each point claims its territory by being nearer than any other. The plane partitions itself.",
             tags=["math", "geometry", "computation"], tile={"accent": "teal"},
             days_ago=14, parent="fano-plane"),
        dict(slug="delaunay-dual", title="Delaunay's Dual",
             excerpt="Connect the sites whose Voronoi cells touch and you have triangulated the plane optimally.",
             tags=["math", "geometry"], tile={"accent": "moss"},
             days_ago=30, parent="voronoi-cells"),
        dict(slug="topo-walk", title="A Walk With Contour Lines",
             excerpt="Stand on a hillside. Every step at the same elevation traces an isoline. Now imagine doing this from a satellite.",
             tags=["geography", "math"], tile={"accent": "sand"},
             days_ago=58),
        dict(slug="road-trip", title="Road Trip Notes",
             excerpt="Eight states, three time zones, one playlist on loop. The interstates are an underrated lattice.",
             tags=["travel"], tile={"accent": "rust"},
             days_ago=92),
        dict(slug="kitchen-tiling", title="Kitchen Tiling Experiment",
             excerpt="A weekend trying to tile a hexagonal kitchen counter without symmetry. It mostly worked.",
             tags=["art", "math"], tile={"accent": "ink"},
             days_ago=140),
        dict(slug="sketch-april", title="April Sketches",
             excerpt="Three pages of pen-and-ink fragments. A kestrel; a courtyard; a doorway someone painted blue.",
             tags=["art"], tile={"accent": "moss"},
             days_ago=200),
        dict(slug="winter-letter", title="A Letter From January",
             excerpt="Notes for a friend, half-written, half-abandoned, set down on the windowsill among the dust.",
             tags=["misc"], tile={"accent": "sand"},
             days_ago=320),
        dict(slug="old-puzzle", title="An Old Puzzle Book",
             excerpt="Found in a stack of textbooks. Forty pages of dissection puzzles, signed in the margin, dated 1973.",
             tags=["misc", "math"], tile={"accent": "plum"},
             days_ago=440),
    ]
    base = datetime.now(timezone.utc)
    for s in seeds:
        body = PageCreate(
            title=s["title"], slug=s["slug"],
            content=s["excerpt"], content_type="markdown",
            tags=s.get("tags", []),
            excerpt=s["excerpt"],
            tile=s.get("tile"),
            parent=s.get("parent"),
        )
        # We can't directly set created_at via PageCreate, so retroactively
        # patch pages.json after each create.
        create_page(body)
        # Mutate created_at in-place
        from flubpub.server import load_pages, save_pages, DATA_DIR
        pages = load_pages(DATA_DIR)
        target = base - timedelta(days=s["days_ago"])
        for p in pages:
            if p["slug"] == s["slug"]:
                p["created_at"] = target.isoformat()
                p["updated_at"] = target.isoformat()
        save_pages(DATA_DIR, pages)

    templates = ["quiet-list", "timeline", "voronoi-map", "constellation",
                 "topographic", "mindmap", "marginalia", "gallery"]
    failures = []
    for tmpl in templates:
        slug = f"{tmpl}-index"
        print(f"--- {tmpl} ---")
        path = scaffold(tmpl, slug, work)
        push_full(work, path, slug, f"{tmpl} index")
        if not verify(work, slug):
            failures.append(tmpl)
        print()

    print(f"\nworkspace: {work}")
    print(f"_site:     {work / 'site' / '_site'}")
    if failures:
        print(f"\nFAILURES: {failures}")
        sys.exit(1)
    print("\nAll passed.")


if __name__ == "__main__":
    main()
