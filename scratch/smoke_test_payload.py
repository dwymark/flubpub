"""Smoke test for index_payload pure logic. Run with `uv run python3 scratch/smoke_test_payload.py`."""

import json
from datetime import datetime, timezone

from flubpub.index_payload import (
    build_index_payload,
    parse_index_spec_from_html,
    substitute_pages_marker,
)
from flubpub.models import IndexSpec, IndexFilter, IndexSort


def _page(slug, title, days_ago, tags=None, theme=None, parent=None, content_type=None):
    """Build a mock page dict matching pages.json schema."""
    ts = datetime(2026, 4, 25, tzinfo=timezone.utc).timestamp() - days_ago * 86400
    iso = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
    p = {
        "slug": slug,
        "title": title,
        "created_at": iso,
        "updated_at": iso,
    }
    if tags:
        p["tags"] = tags
    if theme:
        p["theme"] = theme
    if parent:
        p["parent"] = parent
    if content_type:
        p["content_type"] = content_type
    return p


PAGES = [
    _page("voronoi-essay", "Voronoi as Cells", 0, tags=["math", "geometry"]),
    _page("fano-plane", "The Fano Plane", 5, tags=["math"]),
    _page("road-trip", "Road Trip Notes", 10, tags=["travel"]),
    _page("tile-experiment", "A Tiling Experiment", 30, tags=["math", "art"]),
    _page("old-essay", "An Old Essay", 365, tags=["misc"]),
    _page("math-notes", "Math Notes (root)", 1, content_type="index"),
    _page("geometry-essay", "Geometry Sketch", 7, tags=["geometry"], parent="math-notes"),
]


def test(name, predicate):
    print(("PASS" if predicate else "FAIL") + " — " + name)


# Filter by tags_any
spec = IndexSpec(filter=IndexFilter(tags_any=["math"]))
result = build_index_payload(spec, PAGES, self_slug="")
test("tags_any=math returns 3", len(result) == 3)

# Filter by parent
spec = IndexSpec(filter=IndexFilter(parent="math-notes"))
result = build_index_payload(spec, PAGES, self_slug="math-notes")
test("parent=math-notes returns 1 child", len(result) == 1 and result[0]["slug"] == "geometry-essay")

# exclude_self default True
spec = IndexSpec()
result = build_index_payload(spec, PAGES, self_slug="voronoi-essay")
slugs = [p["slug"] for p in result]
test("exclude_self drops voronoi-essay", "voronoi-essay" not in slugs)

# Sort by title asc
spec = IndexSpec(sort=IndexSort(by="title", order="asc"))
result = build_index_payload(spec, PAGES, self_slug="")
titles = [p["title"] for p in result]
test("sort title asc starts with 'A Tiling Experiment'", titles[0] == "A Tiling Experiment")

# Limit
spec = IndexSpec(limit=2)
result = build_index_payload(spec, PAGES, self_slug="")
test("limit=2 returns 2", len(result) == 2)

# Group by year
spec = IndexSpec(group_by="year")
grouped = build_index_payload(spec, PAGES, self_slug="")
test("group_by=year returns sections", isinstance(grouped, list) and "label" in grouped[0])

# kind=index
spec = IndexSpec(filter=IndexFilter(kind="index", exclude_self=False))
result = build_index_payload(spec, PAGES, self_slug="")
test("kind=index returns 1 (math-notes)", len(result) == 1 and result[0]["slug"] == "math-notes")

# URL field added
spec = IndexSpec()
result = build_index_payload(spec, PAGES, self_slug="")
test("url is /<slug>/", all(p["url"] == f"/{p['slug']}/" for p in result))

# Marker substitution
html = '<html><body><script type="application/json" id="flubpub-pages">[]</script></body></html>'
out = substitute_pages_marker(html, '[{"x":1}]')
test("marker substitution replaces []", '[{"x":1}]' in out and "[]" not in out)

# Parse FLUBPUB comment
src = """<!--FLUBPUB
content_type: index
index:
  template: timeline
  filter: { tags_any: [math] }
  limit: 10
-->
<!doctype html>
<html><body></body></html>
"""
spec, stripped = parse_index_spec_from_html(src)
test("parse FLUBPUB returns spec", spec is not None and spec.template == "timeline")
test("parse FLUBPUB strips comment", stripped.lstrip().startswith("<!doctype"))

# No FLUBPUB → None
spec, stripped = parse_index_spec_from_html("<html><body>hi</body></html>")
test("no FLUBPUB → None", spec is None)

print("\nDone.")
