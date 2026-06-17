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

## Strange Interlocutor style switcher

`content/dwm/strange-interlocutor.html` is a **hub**, not a topic index: a
self-contained `html_raw` page that lets a reader pick a reading style and opens
the series essays in it. The choice is a collection-scoped `localStorage` key
(`flubpub:style:strange-interlocutor`) the hub persists, so it follows the
reader across the series. The default style is `wallpaper`.

Each essay has three renditions, one published page per rendition:

| Piece | shader ("Animated") | palm ("Retro") | wallpaper ("Simple", default) |
|---|---|---|---|
| who-were-you-talking-to | `who-were-you-talking-to-field` | `who-were-you-talking-to-palm` | `who-were-you-talking-to` |
| memory-without-a-brain | `memory-without-a-brain` | `memory-without-a-brain-palm` | `memory-without-a-brain-wallpaper` |

The `wallpaper` rendition reuses the base slug where one already serves the
themed essay (who-were-you's base is harbor-themed; memory's base slug is its
`shader` rendition, the convergence page). The `palm` rendition key keeps slug
suffix `-palm` whatever its display label.

The catalogue is `content/dwm/renditions.json` (the SSOT): collection ->
variants (label, accent, blurb) -> pieces -> per-variant published URL, plus the
default variant. **The hub no longer inlines a JS manifest.** It renders the
picker and the piece tiles as static HTML; each tile carries its per-variant
URLs as `data-shader` / `data-palm` / `data-wallpaper` attributes, with the
default `href` set to the wallpaper rendition so the page works with JS off.
The picker renders each style as a small **live preview** in that style's own
idiom: Simple is a serif card on the cool diamond-lattice ground; Retro is a
two-arrow monochrome PDA deck cycling placeholder cards; Animated is the
drifting contour shader (the field rendition's fragment shader, throttled and
DPR-capped) behind a floating text island. The `renditions.json` blurbs now ride
as each option's `aria-label`. Every piece tile and every artifact / depictions
link carries its one-line description plus two authorship marks — `.ai-work`
(who authored the thing) and `.ai-desc` (description written by Claude) — taken
by hand from each page's `description` frontmatter. **These mirror
`renditions.json` and the per-page descriptions by hand; edit both or they
drift** — nothing wires one to the other. The hub's scripts are progressive
enhancement: read the collection key, mark the active style, reskin the hub,
rewrite each tile's `href` from its matching `data-*`, run the preview shader,
and drive the preview deck.

Switching is hub-mediated: the hub repoints its tiles and previews a style by
restyling itself (including a faint patterned ground in wallpaper mode so that
skin's name is honest), and each rendition links back to the hub. A per-page
cross-rendition auto-redirect and an accent-curtain transition are deferred —
the redirect conflicts with palm-eink's no-animation rule and with themed pages
— so a reader changes style from the hub, not from inside a piece.

Palettes and patterns (current): the hub's default `wallpaper` skin is a cool
analogous teal (paper `#e8eef0`, slate ink `#15262d`, teal accent `#0f7d88`)
over a fine teal diamond-lattice ground — distinct from the renditions' harbor
waves. Memory's `wallpaper` rendition is rethemed **content-only**: its
frontmatter now sets `theme: axon` (the wandering-wiring truchet, apt for a
brain-less memory) and its markdown body opens with a `<style>:root{…}</style>`
override to a pink-on-off-white palette (rose accent `#cf3f7e`, plum ink, neutral
off-white — not parchment). The server injects `color_scheme` CSS right after
`<head>`, so a `:root` block in the body wins by source order, and python-markdown
passes the raw `<style>` through unchanged; both verified. This means the retheme
ships via a normal `flubpub push` of the markdown — no theme or `colors.py`
package change. who-were-you's `wallpaper` base stays harbor.

## Unlisted drafts

The main index excludes pages by tag. `home.md`'s index filter carries
`tags_none: [draft, vibe-coded]`, so any page tagged `draft` stays off the
front page while remaining reachable at its own URL. Tagging a page `draft` is
the whole unlisting move on dwm; every Strange Interlocutor page uses it. The
`vibe-coded` tag does the same for toys, which surface on the nonsense index
instead.
