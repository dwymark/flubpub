# Wider Variety of Index Pages — Design Notes

## What "wider variety" means

The gallery index is one fixed layout: square tiles in a grid, fBm shader
backdrop, hand-composed SVG visuals, masthead/footer chrome. To go wider we
need an architecture where many *layout templates* can be written, each
consuming the same data contract and producing a wholly different visual
form: timelines, mind maps, voronoi maps, lists, treemaps, single-line
prompts, "constellation" views, etc.

This document complements `02-nested-index-pages.md`. That doc generalizes
*where* index pages can live (they become a page type). This doc generalizes
*what* index pages can look like.

## The data contract

Every index template — gallery, timeline, list, voronoi, mindmap — consumes
the **same** marker:

```html
<script type="application/json" id="flubpub-pages">[ … pages array … ]</script>
```

The shape inside is a list of page dicts (see `02-nested-index-pages.md`,
optionally grouped). The contract is:

- Each entry has `title`, `slug`, `created_at`, `updated_at`, `url`.
- Optional fields: `theme`, `color_scheme`, `tile {svg,accent,kicker,tags}`,
  `parent`, `excerpt`, `content_type`, plus any future fields.

A template MAY ignore most of these; e.g. a list view only needs
`title/url/created_at`. A template MUST work when optional fields are
absent.

This narrow contract is what makes templates pluggable.

## Template registry

### Templates live as a folder

`templates/<name>/` contains:

```
templates/<name>/
  index.html         # Jinja2 template, consumed by `set-index` / `push`
  index.css          # optional
  index.js           # optional
  README.md          # one paragraph: what this template is for
  vars.example.yml   # optional sample vars
```

The current `templates/gallery-index.{html,css}` and
`templates/gallery-{shader,tiles}.js` migrate to `templates/gallery/`.

### Naming and registration

Template names must match `[a-z0-9-]+`. They're registered implicitly: any
folder under `templates/` with an `index.html` is a template. No central
registry file — discovery is filesystem-based, like flubpub's themes.

`flubpub list-index-templates` lists them.

### A template can declare what it consumes

In a comment at the top of `index.html`:

```html
<!--FLUBPUB-TEMPLATE
name: timeline
description: "Vertical timeline grouped by year. Reads created_at and tile.accent."
data:
  required: [title, slug, created_at, url]
  optional: [tile.accent, theme, tags]
  group_by_supported: [year, month]
vars:
  - { name: brand,   default: "" }
  - { name: tagline, default: "" }
-->
```

Used for tooling (validation, autocompletion, the `list-index-templates` UI).
Not enforced at runtime — the contract is "consume the marker, do whatever."

## How a template gets used

Two paths, both already implied by the nested-index doc:

1. **As a normal page**: write/copy a template into a working file, edit
   contents, then `flubpub push my-timeline.html`. The page enters
   `pages.json` with `content_type: index` and an `index:` block.
2. **Via slug-only invocation**: `flubpub push --index-template=timeline
   --title "Math Timeline" --slug math-timeline` — the CLI copies the
   template body, applies vars, and pushes. Faster path for "I want a
   timeline of all math posts" without manually editing HTML.

### Authoring with a template

```bash
uv run flubpub new-index --template timeline --slug recent-essays \
    --vars vars.yml > recent-essays.html
# user edits recent-essays.html, tweaks the index spec
uv run flubpub push recent-essays.html
```

`new-index` is sugar — pure local file generation, no server interaction.

## Decoupling the renderer from the data shape

A template might want a *transformed* payload — a histogram of post counts
per week, or a graph of (post → linked post) edges. We expose this via a
**payload-shaper** identifier in the index spec:

```yaml
index:
  template: histogram
  shaper: weekly-counts     # named function in flubpub.shapers
```

`flubpub.shapers` is a small module of pure functions:

```python
def flat(pages, spec) -> list[dict]: ...           # default
def grouped(pages, spec) -> list[dict]: ...        # uses spec.group_by
def weekly_counts(pages, spec) -> dict: ...        # for histogram
def link_graph(pages, spec) -> dict: ...           # nodes & edges
def voronoi_sites(pages, spec) -> list[dict]: ...  # adds (x,y) per page
def topic_tree(pages, spec) -> dict: ...           # nested by tags
```

Each shaper is named, documented, and hand-rolled. Templates declare which
shaper they want. Authors can add new shapers by writing a python function
and registering it via the existing pyproject entry-points or a simple
plugin loader.

When `shaper` is unset, the default is `flat` (today's behavior).

## Theming across templates

Each template can include a `var()` contract — e.g. the gallery template
sets `--paper`, `--ink`, `--muted`, `--gutter`. A template's CSS reads
these custom properties.

Two strategies for picking the values:

1. **Per-template vars file** (existing): `--vars timeline.vars.yml`
   provides Jinja vars and CSS values inlined into `<style>:root { ... }`.
2. **Reuse the existing color scheme system**: the index spec can name a
   color scheme (`color_scheme: parchment`) and the server injects the
   matching `:root { --bg, --fg, --accent-1 }` block into the index page,
   exactly like it already does for themed pages. This is a one-line
   change in `inject_index_pages()` — call `color_scheme_css(scheme)` and
   substitute it into the rendered HTML.

Strategy 2 unifies index pages with themed pages: one set of named color
schemes drives the whole site.

## Asset bundling

Index templates can need assets (fonts, JS, CSS, sprite sheets, font icons).
The existing `set-index` already scans the file for `<img src>`, `<link
href>`, `<script src>`, etc. and uploads them to
`/assets/flubpub-index/`. For named templates, this generalizes to
`/assets/<template-name>/` so multiple index templates don't collide on
asset names.

Concretely:

- `set-index` (root) keeps using `flubpub-index/`.
- `push` of a content_type=index page uses `<slug>/` (existing per-page
  asset namespace). Multiple index pages with overlapping templates each
  get an isolated assets dir.

## Catalogue of templates we plan to ship

Each is a separate small project with its own design philosophy. Detailed
designs in `04-index-page-designs.md`. Headlines:

| Template | Layout primitive | Eye candy | Min field reqs |
|---|---|---|---|
| `gallery` | square tile grid (existing) | fBm shader | tile.svg, tile.accent |
| `quiet-list` | single-column list, italic serif | hairline rules | title, date |
| `timeline` | vertical year-bucket | accent dots | created_at |
| `voronoi-map` | interactive Voronoi cells | live Lloyd relaxation | (x,y) via shaper |
| `topographic` | contour-line backdrop, posts as labels | flowing shader | created_at + tags |
| `constellation` | hash-positioned stars | parallax | slug |
| `mindmap` | hierarchical fan | curved branches | parent |
| `cards-on-table` | tarot-style flip cards | subtle paper grain | tile.svg |
| `archive-shelf` | spine-stack book metaphor | fixed-tile texture | title length |
| `marginalia` | running prose w/ pinned margin notes | none | excerpt |

We ship 5–8 of these in the implementation phase.

## Implementation surface area summary

In `src/flubpub/`:

- `models.py`: add `IndexSpec` Pydantic model, extend `PageCreate`/`PageUpdate`
  with optional `index: IndexSpec` field.
- `server.py`:
  - rename `inject_custom_index` → `inject_index_pages`, generalized as
    described.
  - extract `parse_flubpub_metadata(html_or_md_text)` which extracts the
    `<!--FLUBPUB ... -->` block (HTML) or YAML frontmatter `index:` key
    (MD).
  - extract `build_index_payload(spec, all_pages, self_slug)`.
  - add `apply_shaper(name, pages, spec)` dispatcher.
- `shapers.py` (new): named pure functions for payload shaping.
- `colors.py`: no change.
- `cli.py`:
  - `new-index --template <name>` — generate a working file from a template.
  - `list-index-templates` — discovery output.
  - `index-payload <slug>` — debug helper printing the effective payload.
- `templates/`:
  - migrate `gallery-*` → `gallery/`.
  - add `quiet-list/`, `timeline/`, `voronoi-map/`, `constellation/`,
    `topographic/`, `mindmap/`, etc., per design doc.

In `data/pages.json`: schema gains optional `index` field, no
forward-incompatible changes.

In tests: a few unit tests for `build_index_payload` and `shapers`. The
template HTML is exercised by integration tests that call `set-index` and
spot-check the produced `_site/<slug>/index.html`.

## Why this scales

The architecture has two clean separations:

1. **Where it lives** (any slug, any depth) — addressed by making index a
   page type.
2. **How it looks** (gallery, timeline, voronoi, …) — addressed by the
   template registry + payload shaper.

Adding a new template is then a self-contained activity: one folder under
`templates/`, optionally one new shaper. No core-pipeline changes.
