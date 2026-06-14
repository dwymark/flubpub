# DWM site notes

Per-site context for `content/dwm/` (the danielwymark.com install). Free to
accumulate here without polluting flubpub-tool chats. `bj` will get its own
sibling document when there's anything to say about it.

## Tile metadata (deferred)

Production's `data/pages.json` carries per-page `tile` entries produced by
`/card-construction`. Those don't live in the markdown source. When the
gallery layout starts getting used, commit a sanitized copy of those tile
entries to `content/dwm/tiles.json` so a rebuild-from-content is lossless.
Until then, the gallery is unused and `tiles.json` does not need to exist.

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
  its own slug. `content/dwm/vibe-coded-nonsense.md` lists toys by tag;
  `content/dwm/strange-interlocutor.md` lists a curated series in two described
  `sections`. Publish these with plain `push`, **not** `set-index` — `set-index`
  would overwrite the front page:

  ```bash
  uv run flubpub --site dwm push content/dwm/strange-interlocutor.md
  ```

A topic index resolves its members from the live `pages.json`, so push the
member pages before the index that lists them.

## Unlisted drafts

The main index excludes pages by tag. `home.md`'s index filter carries
`tags_none: [draft, vibe-coded]`, so any page tagged `draft` stays off the
front page while remaining reachable at its own URL. Tagging a page `draft` is
the whole unlisting move on dwm; every Strange Interlocutor page uses it. The
`vibe-coded` tag does the same for toys, which surface on the nonsense index
instead.
