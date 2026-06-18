# DWM site notes

Per-site context for `content/dwm/` (the danielwymark.com install). Free to
accumulate here without polluting flubpub-tool chats. `bj` will get its own
sibling document when there's anything to say about it.

## Tile metadata (deferred)

Production's `data/pages.json` carries per-page `tile` entries produced by
`/card-construction`. Those don't live in the markdown source. The rest of an
html article's pages.json-only metadata (description, tags, ...) is now mirrored
to `content/dwm/_pages.yaml`; when the gallery layout starts getting used, add
the sanitized `tile` entry as another key per slug there so a
rebuild-from-content is lossless. Until then, the gallery is unused and no
`tile` keys exist.

## Vendored project: blockipelago

Upstream: `github.com/dwymark/blockipelago_webgl`, sibling repo at
`../blockipelago_webgl/`.

Vendored at `content/dwm/blockipelago/`. The runtime is four files plus a
`fonts/` dir; the upstream repo's dev cruft (CLAUDE.md, scripts/, notes/,
.git/) is excluded from the snapshot. A `SOURCE` sidecar records provenance in
the standard keyed format (`source_repo` / `source_path` / `source_commit`; see
the Vendoring provenance section in `CLAUDE.md`) — an HTML bundle has no
frontmatter to hold those keys, so the sidecar carries them.

Refresh recipe:

```bash
rsync -av --delete \
  --include='index.html' --include='app.js' --include='data.js' \
  --include='fonts/' --include='fonts/**' --exclude='*' \
  ../blockipelago_webgl/ content/dwm/blockipelago/
{
  echo "source_repo: github.com/dwymark/blockipelago_webgl"
  echo "source_path: runtime bundle (index.html, app.js, data.js, fonts/)"
  echo "source_commit: $( cd ../blockipelago_webgl && git rev-parse HEAD )"
} > content/dwm/blockipelago/SOURCE
```

Publish:

```bash
uv run flubpub --site dwm push content/dwm/blockipelago/index.html \
  --slug blockipelago --title "Blockipelago"
```

`push`'s scanner walks `<style>` blocks for `url(...)` refs, so the two
`@font-face` rules pointing at `fonts/*.ttf` get picked up automatically.
External Google Fonts URLs are skipped (non-local schemes).

## Index pages

dwm runs a main index alongside several topic-oriented indexes. All share the
one index model — an `index:` block in a page's YAML frontmatter, which the
server strips before rendering — and differ in slug and in how they install.

- **Main index** — the site front page, at the reserved root slug. Lives in
  `content/dwm/home.md`. Install it with `set-index`, which routes to the root
  endpoint and writes the front page:

  ```bash
  uv run flubpub --site dwm set-index content/dwm/home.md
  ```

- **Topic indexes** — ordinary pages that also carry an `index:` block, each at
  its own slug. `content/dwm/vibe-coded-nonsense.md` lists toys by tag. Publish
  these with plain `push`, **not** `set-index` — `set-index` would overwrite the
  front page:

  ```bash
  uv run flubpub --site dwm push content/dwm/vibe-coded-nonsense.md
  ```

  The Strange Interlocutor series page is not a topic index but a style-switcher
  hub; see its own section below.

A topic index resolves its members from the live `pages.json`, so push the
member pages before the index that lists them.

## Strange Interlocutor hub

`content/dwm/strange-interlocutor.html` is a **hub**, not a topic index: a
self-contained `html_raw` page that lets a reader pick a reading style and opens
the series essays in it. The choice is a collection-scoped `localStorage` key
(`flubpub:style:strange-interlocutor`) the hub persists, so it follows the
reader across the series. The default style is `shader` (Animated).

Each essay has three renditions, one published page per rendition:

| Piece | shader ("Animated") | palm ("Retro") | wallpaper ("Plain") |
|---|---|---|---|
| who-were-you-talking-to | `who-were-you-talking-to-field` | `who-were-you-talking-to-palm` | `who-were-you-talking-to` |
| memory-without-a-brain | `memory-without-a-brain` | `memory-without-a-brain-palm` | `memory-without-a-brain-wallpaper` |

The `wallpaper` rendition reuses the base slug where one already serves the
themed essay (who-were-you's base is harbor-themed; memory's base slug is its
`shader` rendition, the convergence page). The `palm` rendition key keeps slug
suffix `-palm` whatever its display label.

### Build system (`_hub/`)

The hub is **generated**, not hand-edited. Full rundown in
`content/dwm/_hub/README.md`; in brief, the maintenance surface is three files:

- `_hub/content.jsonl` — the canonical content (lede, the two pieces with full
  glosses and per-rendition slugs, the six artifacts, the depictions link, the
  contributor allocation, the three theme definitions). One JSON object per line.
- `_hub/templates/hub.html.j2` — one Jinja template for every variant. The CSS
  and the flock/shader/deck JS live here verbatim with their comments;
  `{% if js_hub %}` gates the canvas, chooser, deck, and script; the content
  loops fill `#content`, which is both the deck's source and the no-JS column.
- `_hub/build.py` — wiring plus the three baked backgrounds in `_hub/assets/`.

Regenerate after any edit:

```bash
python3 content/dwm/_hub/build.py
```

It writes three self-contained pages into `content/dwm/`:

| output | variant | role |
|---|---|---|
| `strange-interlocutor.html` | JS hub | deck + live chooser; with JS off, falls back to the Animated stacked column |
| `strange-interlocutor-retro.html` | static Retro | no-JS reading column over the gray-dithered flock |
| `strange-interlocutor-plain.html` | static Plain | no-JS reading column over the bird wallpaper |

The no-JS experience is split across the three: each carries a row of theme
links under the lede (styled like the JS chooser, current one depressed) that
navigate between the static variants, so a reader without JS can switch style by
page. The variants differ only in data — background, depressed link, essay
rendition — so the template stays shared. The roomy paged layout of the JS deck
is unchanged. `_hub/` is metadata: `sync` skips any leading-underscore entry, so
it is never deployed as a page, and per-file `push` never deploys it either.

The hub content lives once in a `#content` block: the JS deck reads its sections
and pages them, and without JS the same block is the reading column. Edit
`content.jsonl` and rebuild; both views follow.

Earlier the hub was a cards page driven by `content/dwm/renditions.json` with a
live-style-preview picker. That file is no longer wired to the hub (the content
SSOT is now `_hub/content.jsonl`); the previous hub markup is in git history if
the preview cards are ever wanted again.

### Deploy

Three `html_raw` pages, all unlisted (`draft` + `strange-interlocutor` in
`_pages.yaml`). Deploy each:

```bash
uv run flubpub --site dwm push content/dwm/strange-interlocutor.html
uv run flubpub --site dwm push content/dwm/strange-interlocutor-retro.html
uv run flubpub --site dwm push content/dwm/strange-interlocutor-plain.html
```

The hub's existing slug already carries its title and tags, so its `push` merges
losslessly. The two new pages have entries in `_pages.yaml`; `uv run flubpub
--site dwm sync` deploys all three from `content/` + `_pages.yaml` in one shot,
or pass `--title`/`--tags` on the new pages' first `push`.

### Renditions and rethemes

Bylines are standard across the hub: an `.ai-work` author mark sits under each
title and an `.ai-desc` description mark under each blurb. Unattributed
Claude-generated copy (currently just the lede) uses the `.gen` monospace face
(`--gen`) that flags text Daniel may rewrite. The contributor allocation rides
in a "Who contributed" section (essays, concept, hub, readers, artifacts,
descriptions) with a no-tracking note.

Memory's `wallpaper` rendition is rethemed **content-only**: its frontmatter
sets `theme: axon` (the wandering-wiring truchet, apt for a brain-less memory)
and its markdown body opens with a `<style>:root{…}</style>` override to a
pink-on-off-white palette (rose accent `#cf3f7e`, plum ink, neutral off-white).
The server injects `color_scheme` CSS right after `<head>`, so a `:root` block
in the body wins by source order, and python-markdown passes the raw `<style>`
through unchanged. The retheme ships via a normal `flubpub push` of the markdown
— no theme or `colors.py` package change. who-were-you's `wallpaper` base stays
harbor. The palm readers present the whole essay on one scrollable card (cover,
essay, colophon).

## Unlisted drafts

The main index excludes pages by tag. `home.md`'s index filter carries
`tags_none: [draft, vibe-coded]`, so any page tagged `draft` stays off the
front page while remaining reachable at its own URL. Tagging a page `draft` is
the whole unlisting move on dwm; every Strange Interlocutor page uses it. The
`vibe-coded` tag does the same for toys, which surface on the nonsense index
instead.
