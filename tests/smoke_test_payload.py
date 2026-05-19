"""Smoke test for index_payload pure logic + the unified root-index model.

Run with: PYTHONUNBUFFERED=1 uv run python3 tests/smoke_test_payload.py

Pure, no I/O, fast. Exits non-zero on any failure (CI/agent friendly),
matching the convention of the other tests/smoke_test_*.py.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone

from flubpub.index_payload import (
    build_index_payload,
    parse_index_spec_from_html,
    parse_index_spec_from_markdown,
    substitute_pages_marker,
)
from flubpub.models import IndexFilter, IndexSort, IndexSpec

_failures: list[str] = []


def test(name: str, predicate: bool) -> None:
    status = "PASS" if predicate else "FAIL"
    print(f"{status} — {name}")
    if not predicate:
        _failures.append(name)


def _page(slug, title, days_ago, tags=None, theme=None, parent=None,
          content_type=None):
    ts = datetime(2026, 4, 25, tzinfo=timezone.utc).timestamp() - days_ago * 86400
    iso = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
    p = {"slug": slug, "title": title, "created_at": iso, "updated_at": iso}
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
    # The site front page is now a normal page-type index entry at the
    # reserved slug "index" (unified root-index model).
    _page("index", "Home", 1, content_type="index"),
    _page("geometry-essay", "Geometry Sketch", 7, tags=["geometry"],
          parent="index"),
]


def main() -> None:
    sys.stdout.reconfigure(line_buffering=True)

    spec = IndexSpec(filter=IndexFilter(tags_any=["math"]))
    test("tags_any=math returns 3",
         len(build_index_payload(spec, PAGES, self_slug="index")) == 3)

    spec = IndexSpec(filter=IndexFilter(parent="index"))
    result = build_index_payload(spec, PAGES, self_slug="index")
    test("parent=index returns 1 child",
         len(result) == 1 and result[0]["slug"] == "geometry-essay")

    # The root index excludes itself from its own listing via self_slug.
    spec = IndexSpec(filter=IndexFilter(exclude_self=True))
    slugs = [p["slug"] for p in build_index_payload(spec, PAGES,
                                                    self_slug="index")]
    test("root index excludes its own 'index' entry", "index" not in slugs)

    # A non-root index does NOT drop the root page (no special-casing of the
    # reserved slug in the payload builder — it's just another page).
    spec = IndexSpec(filter=IndexFilter(exclude_self=True))
    slugs = [p["slug"] for p in build_index_payload(spec, PAGES,
                                                    self_slug="fano-plane")]
    test("non-root index still lists the root 'index' page",
         "index" in slugs)

    spec = IndexSpec(sort=IndexSort(by="title", order="asc"))
    titles = [p["title"] for p in build_index_payload(spec, PAGES,
                                                      self_slug="index")]
    test("sort title asc starts with 'A Tiling Experiment'",
         titles[0] == "A Tiling Experiment")

    spec = IndexSpec(limit=2)
    test("limit=2 returns 2",
         len(build_index_payload(spec, PAGES, self_slug="index")) == 2)

    spec = IndexSpec(group_by="year")
    grouped = build_index_payload(spec, PAGES, self_slug="index")
    test("group_by=year returns sections",
         isinstance(grouped, list) and "label" in grouped[0])

    spec = IndexSpec(filter=IndexFilter(kind="index", exclude_self=False))
    result = build_index_payload(spec, PAGES, self_slug="")
    test("kind=index returns 1 (the root)",
         len(result) == 1 and result[0]["slug"] == "index")

    spec = IndexSpec()
    result = build_index_payload(spec, PAGES, self_slug="index")
    test("url is /<slug>/", all(p["url"] == f"/{p['slug']}/" for p in result))

    html = ('<html><body><script type="application/json" '
            'id="flubpub-pages">[]</script></body></html>')
    out = substitute_pages_marker(html, '[{"x":1}]')
    test("marker substitution replaces []",
         '[{"x":1}]' in out and "[]" not in out)

    src = (
        "<!--FLUBPUB\ncontent_type: index\nindex:\n  template: timeline\n"
        "  filter: { tags_any: [math] }\n  limit: 10\n-->\n<!doctype html>\n"
        "<html><body></body></html>\n"
    )
    spec, stripped = parse_index_spec_from_html(src)
    test("parse FLUBPUB returns spec",
         spec is not None and spec.template == "timeline")
    test("parse FLUBPUB strips comment",
         stripped.lstrip().startswith("<!doctype"))

    spec, _ = parse_index_spec_from_html("<html><body>hi</body></html>")
    test("no FLUBPUB → None", spec is None)

    md = "---\ntitle: Home\nindex:\n  sort: { by: manual }\n---\n# Home\n"
    spec, stripped = parse_index_spec_from_markdown(md)
    test("parse md frontmatter index returns spec",
         spec is not None and spec.sort.by == "manual")
    test("parse md frontmatter strips block",
         stripped.lstrip().startswith("# Home"))

    print()
    if _failures:
        print(f"FAILURES ({len(_failures)}):")
        for f in _failures:
            print(f"  - {f}")
        sys.exit(1)
    print("All passed.")


if __name__ == "__main__":
    main()
