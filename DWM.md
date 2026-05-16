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
.git/) is excluded from the snapshot. A `SOURCE` file records the upstream
sha at vendoring time.

Refresh recipe:

```bash
rsync -av --delete \
  --include='index.html' --include='app.js' --include='data.js' \
  --include='fonts/' --include='fonts/**' --exclude='*' \
  ../blockipelago_webgl/ content/dwm/blockipelago/
( cd ../blockipelago_webgl && git rev-parse HEAD ) > content/dwm/blockipelago/SOURCE
```

Publish:

```bash
uv run flubpub --site dwm push content/dwm/blockipelago/index.html \
  --slug blockipelago --title "Blockipelago"
```

`push`'s scanner walks `<style>` blocks for `url(...)` refs, so the two
`@font-face` rules pointing at `fonts/*.ttf` get picked up automatically.
External Google Fonts URLs are skipped (non-local schemes).

## Custom index spec

Lives in `content/dwm/home.md` as YAML frontmatter under the `index:` key,
not as a separate file. The server strips it before rendering.

Re-install the index after edits:

```bash
uv run flubpub --site dwm set-index content/dwm/home.md
```
