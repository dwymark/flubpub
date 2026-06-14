---
name: nonsense
description: Use when the user wants to add a new vibe-coded toy/app to the "Vibe-coded nonsense" collection on danielwymark.com — copies the HTML into the dwm SSOT, injects an on-page authorship disclosure, writes a badged listing blurb, and pushes to production. Invoke on "add <file> to the nonsense list", "publish this vibe-coded app", "put <toy> on the nonsense page".
---

# Adding a vibe-coded app to the nonsense list

"Vibe-coded nonsense" is a page-type index at slug `vibe-coded-nonsense` on the
dwm site. It lists every page tagged `vibe-coded`, ordered by a manual sort in
`content/dwm/vibe-coded-nonsense.md`. The home page hides that tag, so adding a
toy here keeps it off the front page automatically.

Input: a self-contained HTML artifact (one file, no external assets is the easy
case). Output: the toy in `content/dwm/`, disclosed on-page, pushed to dwm, and
showing in the index with a badged one-line blurb.

## When to invoke

- "Add ~/Downloads/<toy>.html to the nonsense list"
- "Publish this vibe-coded app / put it on the nonsense page"
- "Add <toy> to vibe-coded nonsense and push"

Not for: non-vibe pages, the home page, research, or theme/index plumbing.

## Procedure

1. **Name it.** Pick a kebab-case `<slug>` and a human `<title>`. Copy the file
   to `content/dwm/<slug>.html` (the SSOT). If it has sibling assets, copy them
   alongside and let flubpub's bundle upload carry them.

2. **Pick a disclosure format** by how the page is built:
   - **banner** — scrolling/document-like pages (an essay, a card grid, an
     atlas). Sits at the top, collapses to a compact line. Needs a `<body>` tag.
   - **stamp** — immersive full-screen pages (a canvas/WebGL/SVG toy). A small
     corner pill that expands to a panel. Choose a `--corner` (tr/br/tl/bl) that
     the toy's own UI leaves free.
   - **dock** — immersive pages whose corners are busy. A bottom-center tab that
     expands upward. Works on tagless minimal HTML (no `<body>` needed).

   Inject it (idempotent; safe to re-run):
   ```bash
   uv run python3 .claude/skills/nonsense/assets/disclose.py \
       --file content/dwm/<slug>.html --format stamp --corner br \
       --head "Who made this?" \
       --body "A vibe-coded toy, made with Claude (Anthropic) under Daniel Wymark's direction. It runs entirely in your browser, with no network calls and no storage."
   ```
   Keep the body to one or two honest sentences (allocation or dialogue shape,
   per the /disclosure skill). Add a one-line behavior note when the page runs
   code that touches the network or stores anything; these toys are client-only,
   so "runs in your browser, no network, no storage" is the usual line. All three
   formats are no-JS, dismissable, and leave a persistent marker.

3. **Write a listing blurb + badge.** One sentence describing the toy, followed
   by the inline Claude badge. The badge is raw HTML carried in the page's
   `--description` (flubpub injects descriptions into the index list unescaped):
   ```
   <span class="ai-tag" title="This blurb was written by Claude (Anthropic), not by Daniel.">🤖 Claude</span>
   ```
   The `.ai-tag` CSS lives in the `<style>` block at the top of
   `content/dwm/vibe-coded-nonsense.md`; the badge inherits it there.

4. **Push to dwm.** Tag `vibe-coded` and pass the badged description:
   ```bash
   uv run flubpub --site dwm push content/dwm/<slug>.html \
       --slug <slug> --title "<Title>" --tag vibe-coded \
       --description "<one-line blurb> <BADGE-HTML>"
   ```
   For an existing slug use `revise <slug> <file>` instead of `push`. Always
   re-pass `--tag vibe-coded` on a revise — revise with no `--tag` clears tags.

5. **Order it (optional).** Add `<slug>` to the `index.sort.manual` list in
   `content/dwm/vibe-coded-nonsense.md`, then
   `uv run flubpub --site dwm revise vibe-coded-nonsense content/dwm/vibe-coded-nonsense.md`.
   Membership is by tag, so this only controls position; an untouched list still
   shows the toy, sorted after the named ones.

6. **Verify live.**
   ```bash
   curl -s -o /dev/null -w "%{http_code}\n" https://danielwymark.com/<slug>/
   curl -s https://danielwymark.com/vibe-coded-nonsense/ | grep -c 'class="ai-tag"'   # entry count
   curl -s https://danielwymark.com/<slug>/ | grep -c dwm-disc                        # disclosure present
   ```

7. **Commit** `content/dwm/` (the changed/added artifact, and the index file if
   reordered). Plain-prose message naming the toy.

## Notes

- The on-page disclosure formats and the inline badge originate from the
  `/disclosure` skill's web tool (full-screen and inline cases it had left
  deferred). `assets/disclose.py` is the concrete implementation for this site.
- Known SSOT gap: a `.html` page's `vibe-coded` tag and its badged description
  live in the remote `pages.json`, not in `content/`. A rebuild purely from
  `content/` (e.g. `flubpub sync`) would not re-tag or re-badge it. The index's
  manual sort list in `vibe-coded-nonsense.md` is the one durable record of
  membership.
