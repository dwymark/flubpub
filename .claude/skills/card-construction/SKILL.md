---
name: card-construction
description: Use when the user asks to design, build, iterate, or commit a gallery tile (card) for a flubpub page — turns a published post into an approved `tile` entry on `data/pages.json`. Runs a five-phase loop (analyze → generate → present → feedback → commit) with annotated SVG mockups as the feedback medium.
---

# Card construction for flubpub gallery tiles

The flubpub gallery index (`templates/gallery-index.html` + `gallery-tiles.js`) renders one 260×260-ish card per published page. Default cards are an italic monogram over a quiet frame. This skill replaces those with hand-composed SVG cards that extend the post's subject matter into a small visual object.

Input: a page slug that already exists in `data/pages.json`.
Output: an approved `tile: { accent, svg, kicker, tags }` merged into that page's entry, the local index rebuilt, and the concept history archived to `.cards/<slug>/`.

## When to invoke

Use this skill when the user asks to:
- "Build a card / tile for <page>"
- "Design a gallery tile for <slug>"
- "Give <post> a proper card"
- "Iterate on the tile for <slug>" (resumes an existing `.cards/<slug>/` if present)

Do not use this skill for tasks unrelated to the `tile` metadata contract (theme design, colour scheme edits, shader tweaks).

## Tile contract (non-negotiable)

Before generating anything, read `references/tile-contract.md` and `references/accents.md`. Every SVG you produce must pass the contract checklist. Non-compliant SVGs will render wrong or break the gallery.

Summary of the contract:
- `<svg viewBox="0 0 160 160" preserveAspectRatio="xMidYMid meet">` — no width/height, no namespaces.
- Inline attributes only. No `<style>`, no `<defs>` that reference external resources, no `<image>`, no `<script>`.
- Text uses `font-family="Cormorant Garamond, Georgia, serif"` or `Inter` or `JetBrains Mono` (loaded by the gallery page).
- Each annotatable visual element wraps in `<g data-anno-id="N" data-label="…">…</g>` where `N` is a small integer, unique within the concept.
- Accent colour is one of: `rust`, `teal`, `sand`, `ink`, `moss`, `plum`.
- `kicker` ≤ 18 chars, `tags` ≤ 48 chars, `title` (from pages.json) is rendered by the template — do not duplicate it inside the SVG.

See `references/svg-idioms.md` for good patterns and failure modes.

## Five phases

The loop is:

1. **Analyze** — read the post, extract themes.
2. **Generate** — produce three distinct concepts with annotated SVGs.
3. **Present** — instantiate a side-by-side viewer for human review.
4. **Feedback** — interpret comments against concept letters and annotation IDs; iterate.
5. **Commit** — write the approved tile into `data/pages.json`, archive everything else, trigger a rebuild.

Do not skip phases. Even if the user asks for one concept, produce three — the contrast is the point. Iteration in phase 4 can collapse to the chosen direction.

### Phase 1 — Analyze

Given slug `S`:

1. Confirm `data/pages.json` has an entry for `S`. If not, stop and tell the user.
2. Read the source file at `site/src/pages/S.md` or `site/src/pages/S.html`. If HTML, strip chrome/layout and focus on content.
3. Create `.cards/S/` (directory is gitignored already).
4. Write `.cards/S/brief.md` with:
   - **Topic** — one sentence.
   - **Central metaphors / motifs** — 2–5 items, each pointing to a line or phrase in the source.
   - **Tone** — essay / note / code / photo / list / experiment / marginalia.
   - **Structural shape** — notable structural features (long code block, pull quote, ordered list of steps, photo grid…).
   - **Proper nouns and concrete objects** — candidates for iconography.
   - **What the tile should *not* be** — explicit rejections (e.g. "not a literal screenshot", "not a pun").
   - **Suggested accents** — 2 or 3 from the palette with one-line rationales.

The brief is short. One page. It constrains phase 2.

### Phase 2 — Generate

Produce three distinct concepts. "Distinct" means: different visual grammar, different accent, different reading of the source. Not three colour variations of one idea.

For each concept, decide:
- `id` — `A`, `B`, or `C`.
- `accent` — from the six.
- `kicker` — short label (e.g. "Essay", "Marginalia", "Field note"). Prefer something specific to the post over the post's `theme` field.
- `tags` — 1 to 3 short items joined by ` · ` (middle dot, U+00B7). Optional; omit if nothing honest to say.
- `svg` — pure SVG per contract. Wrap each meaningful visual element in `<g data-anno-id="N" data-label="…">`.
- `rationale` — 2–4 sentences: what the composition is saying and why it fits the brief.
- `annotations` — array of `{id: N, label: "…"}` entries that mirror the `<g>` wrappers.

Write all three concepts to `.cards/S/concepts.json` as:

```json
{
  "slug": "S",
  "brief_ref": "brief.md",
  "concepts": [
    {"id": "A", "accent": "…", "kicker": "…", "tags": "…",
     "svg": "<svg …>…</svg>", "rationale": "…",
     "annotations": [{"id": 1, "label": "…"}, …]},
    …
  ]
}
```

**Contract check:** before writing the file, re-read `references/tile-contract.md` and validate each SVG against the checklist. Fix violations before proceeding.

### Phase 3 — Present

Copy `assets/viewer-template.html` to `.cards/S/viewer.html`. The template is self-contained except for one thing it pulls in by relative path:
- `../../templates/gallery-index.css` — so the tiles render as they will in production.

The viewer reads two inline JSON payloads. After copying, substitute both placeholders:

- `/* CONCEPTS_JSON */` inside `<script id="concepts">` — the exact JSON from `concepts.json`.
- `/* META_JSON */` inside `<script id="meta">` — an object `{ "slug": "S", "title": "…", "brief": "…plain text of brief.md…", "post_url": "http://localhost:8000/S/" }`. `post_url` is optional; when omitted, the viewer defaults to `http://localhost:8000/<slug>/` (the local `flubpub serve` default).

Keep both script tags and their `type="application/json"` attributes intact.

**Serve, do not file://.** The viewer must be loaded over HTTP so the stylesheet at `../../templates/gallery-index.css` resolves and so the post-link works. Start a server at the repo root (`python3 -m http.server 8801` run in background) and open `http://localhost:8801/.cards/S/viewer.html`. The flubpub server must also be running on port 8000 for the "view post" link to resolve.

The viewer shows:
- Post title + link to the live page.
- The brief, collapsed by default.
- Three tiles rendered at ~260px square side by side, exactly as the gallery would render them.
- A toggle: **Show annotations**. When on, numbered badges appear over each `<g data-anno-id>` element (positioned at the element's `getBBox()` centre), and a numbered legend appears alongside each tile.
- Each tile has a per-concept rationale box.

Tell the user the viewer is ready and how to open it. Prefer `wslview .cards/S/viewer.html` on WSL (per user convention).

### Phase 4 — Feedback

The user will respond in one of three modes:

- **Approve one concept** — "B is it" / "ship C". Proceed to phase 5.
- **Iterate on one** — "B but swap the moss for sand and drop element 3". Bump a new revision file at `.cards/S/iterations/vN.json` (v1, v2, …) with the revised concept(s) only. Update the viewer's JSON payload in place so the user can re-open the same viewer file and see the change.
- **Start over** — "none of these land, try again". Keep the original `concepts.json` as `concepts-v0.json`, generate fresh, and restart phase 3.

Parse references unambiguously:
- Concepts are `A`, `B`, `C` (case-insensitive).
- Annotation numbers refer to `data-anno-id` values within that concept — e.g. "A3" or "concept A element 3" both mean `A.annotations[id=3]`.
- Colour adjustments should map onto the accent palette; if the user names a raw hex, choose the nearest of the six.

If a comment is ambiguous, ask one clarifying question before iterating. Do not guess.

### Phase 5 — Commit

Once a concept `X` is approved:

1. Validate `X.svg` one more time against the tile contract.
2. Open `data/pages.json`, find the entry with `slug == S`, and add or replace the `tile` field:
   ```json
   "tile": {
     "accent": "…",
     "svg": "<svg …>…</svg>",
     "kicker": "…",
     "tags": "…"
   }
   ```
   Use the `Edit` tool with enough surrounding context for the match to be unique. Keep field order stable.
3. Write `.cards/S/final.json`:
   ```json
   {
     "slug": "S",
     "approved": "X",
     "tile": {…the committed tile…},
     "rejected": [
       {"id": "A", …full concept…},
       {"id": "C", …full concept…}
     ],
     "iterations": [list of vN.json filenames],
     "approved_at": "<ISO-8601 UTC>"
   }
   ```
4. Trigger a local rebuild so the result is visible immediately:
   ```bash
   uv run flubpub set-index templates/gallery-index.html
   ```
   This re-stamps the custom index (idempotent) and triggers `rebuild_site`, which re-injects the fresh `pages.json` payload. The new tile appears at `http://localhost:<port>/` once the server rebuild completes.
5. Report to the user: which concept shipped, where the rejected variants are archived, and the exact command for remote deploy. Deployment to production is out of scope for this skill — the user runs `deploy.sh` or rsyncs `data/pages.json` themselves.

## Resuming an existing card

If `.cards/S/` already exists when the user asks to iterate:

- If `final.json` is present, the tile has already shipped. Ask: are we revising the approved tile, or archiving and starting from scratch? If revising, load `final.json` into phase 4 as the current state and accept feedback against it.
- If only `concepts.json` is present, we're mid-loop. Load it into phase 3 (regenerate viewer if missing) and continue.

## Working conventions

- **Do not touch** `templates/gallery-index.html`, `gallery-tiles.js`, `gallery-shader.js`, or `gallery-index.css` from this skill. Those are the rendering contract, not content.
- **Do not push to the server** or invoke `flubpub push/revise/delete`. Those write page files; this skill writes metadata.
- **One page at a time.** If the user asks for tiles on several pages, run the loop once per slug serially. Concept generation for different pages should not share state.
- **Commit scope:** only `data/pages.json` and the `.cards/` tree are touched. `.cards/` is gitignored, so nothing there gets committed. `data/pages.json` may or may not be committed depending on the project's policy — ask the user if uncertain.
- **No emojis** in briefs, concepts, rationale, or tile contents unless the user explicitly asks.
- **Preserve post URLs.** Each tile is an `<a href="/slug/">`. The slug is the `S` you already have; do not rewrite it.

## Reference files

- `references/tile-contract.md` — exact schema, SVG rules, validation checklist.
- `references/accents.md` — the six accents with hex values and mood notes.
- `references/svg-idioms.md` — patterns that work, anti-patterns that break rendering.
- `assets/viewer-template.html` — side-by-side viewer with annotation toggle.

Read `references/` before producing concepts. The viewer template is copied, not edited, in phase 3.
