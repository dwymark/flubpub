# Tile contract

This document is the authoritative schema for `tile` metadata written into `data/pages.json`. It mirrors the consumer in `templates/gallery-tiles.js` — if you change this file, the consumer has already changed too; if not, you have a bug.

## JSON schema (informal)

```jsonc
{
  // All fields optional. When absent, gallery-tiles.js falls back to a hash-seeded monogram.
  "tile": {
    "accent": "rust" | "teal" | "sand" | "ink" | "moss" | "plum",
    "svg":    "<svg viewBox=\"0 0 160 160\" preserveAspectRatio=\"xMidYMid meet\">…</svg>",
    "kicker": "string, ≤ 18 chars",
    "tags":   "string, ≤ 48 chars, middle-dot separated"
  }
}
```

A partial tile is legal: e.g. `{ "accent": "teal", "kicker": "Field note" }` keeps the monogram default but uses the chosen accent + kicker. For a hand-composed card, supply all four fields.

## SVG rules

The SVG string is inlined into the rendered HTML without sanitization. Every rule here protects the gallery page from breaking.

**MUST:**
- Start with `<svg viewBox="0 0 160 160" preserveAspectRatio="xMidYMid meet">`.
- Be valid, self-closing, parseable XML (every tag closed, attributes quoted).
- Use only geometric primitives (`rect`, `circle`, `ellipse`, `line`, `polyline`, `polygon`, `path`) and `text`/`tspan`/`g`.
- Wrap every meaningful visual element in `<g data-anno-id="N" data-label="…">…</g>` where `N` is a small integer unique within this SVG. Background textures that are not semantically separable (a wash of dots, a subtle frame) do not need annotation — skip them.

**MUST NOT:**
- Include `<style>`, `<script>`, `<image>`, `<foreignObject>`, `<iframe>`, or external references (`href` on `use`, `xlink:href`, `url()` outside colour contexts).
- Set `width` or `height` on the root `<svg>` — CSS sizes it.
- Include XML declarations, `xmlns:xlink`, DOCTYPE, or comments.
- Reference any font other than `Cormorant Garamond, Georgia, serif`, `Inter`, or `JetBrains Mono`. These are the three families loaded by the gallery page.
- Use CSS variables (`var(--…)`). The gallery CSS provides the accent via `data-accent`, but the SVG itself must use concrete hex values.
- Contain the page title. The `<h2 class="title">` below the SVG already shows it.

**SHOULD:**
- Use 2–8 `<g data-anno-id>` wrappers. Too few makes the feedback phase flat; too many makes the legend unreadable.
- Keep stroke widths between 0.4 and 2.0. Above that, the composition looks blunt at 260px.
- Treat the accent colour as the lead and let it carry most of the ink. Secondary strokes in `#1a1a1e` or `#8a8579` are fine.
- Leave a 10–14 unit margin inside the 160×160 viewBox for the frame.

## Accent mapping

The browser-side renderer uses the `data-accent` attribute on the tile anchor to look up the accent colour via CSS. Inside your SVG, hardcode the hex value for visual fidelity. The six authorized values are in `accents.md`.

## Kicker and tags

- `kicker` appears top-left in the tile with a small swatch dot. It's a label, not a sentence. Examples: `Essay`, `Marginalia`, `Field note`, `Sketch`, `Problem set`, `Recipe`, `Obituary`.
- `tags` appears at the bottom of the tile in monospace, in small caps. Middle dots separate items. Examples: `recursion · geography · 8 min`, `vim · quiet`, `1964 · tennessee`.

If you can't write a precise kicker, use the page's theme name capitalized (that's the default). If you can't write tags, omit the field.

## Validation checklist

Run through this before writing `concepts.json` or committing to `pages.json`:

1. [ ] `viewBox="0 0 160 160"` exact, `preserveAspectRatio="xMidYMid meet"` exact.
2. [ ] No `width`/`height` on the root `<svg>`.
3. [ ] Parses as XML. (Mentally trace open/close tags.)
4. [ ] No `<style>`, `<script>`, `<image>`, `<foreignObject>`.
5. [ ] No `xmlns:xlink`, no `xlink:href`, no `href` on `<use>`.
6. [ ] Every `<g data-anno-id="N">` has a unique `N` and a non-empty `data-label`.
7. [ ] All text uses one of the three permitted font families.
8. [ ] Accent is one of the six authorized keys.
9. [ ] Kicker length ≤ 18, tags length ≤ 48.
10. [ ] Title of the post does not appear inside the SVG.
11. [ ] Colours inside the SVG are concrete hex values, not CSS variables.
12. [ ] SVG renders cleanly when the string is substituted into a test `<div>` — mentally simulate the paint order.

A concept that fails any item is rejected by this skill and re-generated.
