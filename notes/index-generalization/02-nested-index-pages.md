# Nested Index Pages — Design Notes

## What we have today

The current system supports **exactly one** custom index, mounted at `/`:

- `flubpub set-index <html>` writes the rendered template to
  `data/custom_index.html`.
- `inject_custom_index()` in `server.py` substitutes the marker
  `<script id="flubpub-pages">` with **all** pages from `pages.json` sorted
  `created_at desc` and writes the result to `_site/index.html`,
  overriding 11ty's default.
- Removal: `flubpub unset-index` deletes `custom_index.html`.

Two limitations follow:

1. There can be only one custom-index page on the entire site.
2. The page list inside the marker is always *all* pages, sorted by date desc.

## Goal

Make index pages a **first-class page type** — they live at any slug, can be
nested inside the chronology of normal pages, can be created via `push` /
`revise` / `delete` like any other page, and the listing they render is
**configurable**: filtered, sorted, capped, and shaped however the index
declares it should be.

## Data model changes

### `pages.json` per-entry additions

A page becomes an *index page* when it carries an `index:` block:

```yaml
slug: math-notes
title: "Math Notes"
content_type: index            # new: page-type tag
index:
  template: gallery            # which renderer to use (filename in templates/)
  vars:                        # optional Jinja vars (same as set-index --vars)
    brand: "Math Notes"
    tagline: "essays & sketches"
  filter:                      # which pages to include
    tags_any: [math, geometry]
    tags_all: []
    theme: ~
    content_type: ~
    after: 2026-01-01
    before: ~
    slug_glob: "math-*"
    exclude_self: true         # almost always true
  sort:                        # ordering
    by: created_at             # | title | random | manual
    order: desc                # | asc
    seed: ~                    # for random
    manual: []                 # explicit slug list, used when by=manual
  limit: 50                    # cap, ~ for unlimited
  group_by: ~                  # optional — see "Sections / Groups" below
```

Every field has a sensible default; the minimum spec is

```yaml
content_type: index
index: { template: gallery }
```

which gives "all pages, newest first" — matching today's behavior.

### `tile:` already exists per page

Index pages use the existing `tile` field (svg/accent/kicker/tags). Nothing to
change.

### New page-type detection

`content_type` gains a value `index`. The server stores the page like any
other HTML page (it *is* HTML — just with the marker), and at rebuild-time
`inject_pages_marker()` runs over **every** index page, not just the root one.

## Rendering pipeline

### Generalize `inject_custom_index` → `inject_index_pages`

```python
def inject_index_pages():
    """For each page with content_type == 'index', read its rendered HTML from
    _site/<slug>/index.html, substitute the #flubpub-pages marker with the
    filtered+sorted+limited payload, and write it back."""
    pages = load_pages(DATA_DIR)
    for entry in pages:
        if entry.get("content_type") != "index":
            continue
        out_path = SITE_OUTPUT / entry["slug"] / "index.html"
        if not out_path.exists():
            continue
        spec = entry.get("index", {})
        payload = build_index_payload(spec, pages, self_slug=entry["slug"])
        html = out_path.read_text()
        html = substitute_pages_marker(html, payload)
        out_path.write_text(html)
    # Backwards compat: the existing root custom-index path still applies.
    inject_root_custom_index()
```

`build_index_payload(spec, all_pages, self_slug)` returns the filtered/sorted
list of page dicts (with `url` filled in), respecting all the knobs in
`spec`. This is pure-python with no I/O — easy to unit test.

### Where the index page comes from

Two paths for creating an index page:

1. **Via push**: `flubpub push my-index.html --title "Math Notes"`.  The HTML
   carries an `index:` block in its frontmatter / `data-flubpub-index` head
   tag. The server detects the marker `<script id="flubpub-pages">` in the
   uploaded HTML and stores it as a `content_type=index` page with the parsed
   index spec.
2. **Via the existing set-index** (root only, kept for backward compatibility):
   `flubpub set-index ...` continues to set the *root* index. Internally it
   creates a synthetic index page with `slug=""`.

The cleaner path going forward is (1). (2) is sugar.

### Frontmatter format

For `.html` index pages:

```html
<!--FLUBPUB
content_type: index
index:
  template: gallery
  filter: { tags_any: [math] }
  sort: { by: created_at, order: desc }
  limit: 24
-->
<!doctype html>
...rest of the index template...
```

The server parses the `<!--FLUBPUB ... -->` block, strips it before storing,
and persists the `index:` block on the `pages.json` entry.

For `.md` pages, use frontmatter:

```yaml
---
title: Math Notes
content_type: index
index:
  template: gallery
  ...
---
```

## CLI surface additions

```bash
# Push a new index page like any other page
uv run flubpub push math-index.html --title "Math Notes"

# List index pages specifically
uv run flubpub list --kind index

# Show effective filter/payload (useful for debugging)
uv run flubpub index-payload math-notes
```

## URL routing

Index pages live at `/<slug>/`, exactly like normal pages. The 11ty pipeline
already produces `_site/<slug>/index.html` for every `.html` page in
`site/src/pages/` — we don't need new routing. The injection step just
post-processes those files.

This is the cleanest part of the design: by treating index pages as regular
pages with a marker, we inherit URL routing, asset uploading, sub-page
linking, and revision history "for free."

## Sections / Groups

When `group_by` is set, the payload becomes a list of sections instead of a
flat array:

```json
[
  {"label": "2026", "pages": [...]},
  {"label": "2025", "pages": [...]}
]
```

Available group-by axes:

- `year`, `month`, `quarter` — derived from `created_at`
- `theme` — the page's theme name
- `color_scheme` — likewise
- `tags[0]` — first tag
- `kind` — `index` vs not, useful for "site map" pages
- a JSONPath / dotted-path expression for arbitrary nested fields, e.g.
  `tile.accent`

The renderer template can branch on whether the payload is a list-of-pages
(flat) or a list-of-sections (grouped) by inspecting the marker contents.

## Filtering vocabulary (cheat sheet)

| Knob | Type | Effect |
|---|---|---|
| `tags_any` | list[str] | include if page's tag list intersects |
| `tags_all` | list[str] | include only if page has all tags |
| `tags_none` | list[str] | exclude if any tag matches |
| `theme` | str \| list[str] | match by theme |
| `color_scheme` | str \| list[str] | match by color scheme |
| `content_type` | str \| list[str] | filter by type |
| `slug_glob` | str | shell-style glob on slug |
| `slug_regex` | str | regex match (mutually exclusive with glob) |
| `before` / `after` | ISO date | bound by `created_at` |
| `parent` | slug | only direct children of a given page (see "Tree topology") |
| `exclude_self` | bool | drop the index page itself from its own listing (default true) |
| `kind` | `"index"` \| `"page"` | filter on page type |

## Tree topology — optional

A page can declare a `parent: <slug>` in its metadata. An index page can then
filter `parent: <self.slug>` to render only its direct children. This makes
nested index hierarchies possible without computing them ad-hoc:

```
/                    -- root index, no filter
/math/               -- index, parent: math, lists everything tagged math
/math/geometry/      -- index, parent: geometry, lists geometry essays
/math/geometry/voronoi-essay  -- a normal page with parent: geometry
```

The `parent` field is metadata on the *child* page. The index uses `filter:
{parent: <self_slug>}` to grab its children. This is the same shape as
filesystems and feels natural.

## Backwards compatibility

The current `set-index` flow:

1. `flubpub set-index gallery-index.html` → still writes
   `data/custom_index.html` AND/OR creates a synthetic root index page.
2. `inject_custom_index()` is renamed to `inject_index_pages()` but a thin
   wrapper preserves the old name for any deployment scripts.
3. Existing `pages.json` entries without `content_type: index` are unaffected.

Migration script: a `flubpub migrate-root-index` that converts the existing
`data/custom_index.html` into a synthetic page entry with `slug=""` (or
`slug="index"`). Idempotent and one-shot.

## Open questions

- **Nested URL collisions**: does `/math/voronoi/` need to be a real subpath,
  or is it sufficient that all pages live at `/<slug>/` with a flat URL space?
  Recommend: keep flat. Slugs encode structure (`math-voronoi`,
  `math-geometry`); `parent` encodes parentage in metadata only. URL
  hierarchy is harder than it looks (how does 11ty resolve relative refs?).
- **Caching of payloads**: rebuilding a 1000-page site with 20 index pages
  re-filters the page list 20 times per rebuild. At our scale this is
  microseconds — don't optimize until measured.
- **Index of indexes**: an index page can render other index pages (filter on
  `kind: index`). Tested by including the root index's tile in itself and
  ensuring `exclude_self` works.
- **SSR vs client hydration**: the gallery template hydrates client-side from
  the JSON marker. Some new templates (e.g. a list view) might want pure SSR
  so the page works without JS. Both are fine — the marker is just a
  contract; what the template *does* with the JSON is its choice. Templates
  that don't need JS can omit the marker and rely on Jinja vars instead.
