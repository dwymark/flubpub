# SVG idioms for tile composition

Patterns that read well at 260px, and patterns that don't. All examples use the 160×160 viewBox.

## Good patterns

### 1. The framed object

A 136×136 inner rectangle (x=12, y=12) and a single object centred inside. Works for near everything.

```xml
<svg viewBox="0 0 160 160" preserveAspectRatio="xMidYMid meet">
  <g data-anno-id="1" data-label="quiet frame defining the card's window">
    <rect x="12" y="12" width="136" height="136"
          fill="none" stroke="#c44a2a" stroke-width="0.6" opacity="0.55"/>
  </g>
  <g data-anno-id="2" data-label="central object — a single italic glyph standing in for the subject">
    <text x="80" y="112" text-anchor="middle"
          font-family="Cormorant Garamond, Georgia, serif"
          font-size="96" font-style="italic" font-weight="500"
          fill="#c44a2a" opacity="0.78">r</text>
  </g>
</svg>
```

### 2. The diagram fragment

A tiny schematic: two or three shapes connected by lines, like a miniature whiteboard sketch. Good for systems posts.

- Nodes: `<circle r="6">` or small rounded rects.
- Edges: `<path d="M… Q… …" stroke-linecap="round">`. Quadratic beziers read softer than straight lines.
- Labels: monospace, `font-size="7"`, sparing.

### 3. The typographic seal

A block of small caps or mixed-weight text arranged as an object — a date, a place, a measurement. Good for field notes, poems, obituaries. Keep to 2–4 lines max.

### 4. The pattern fragment

A repeating motif (dots, ticks, a wave) cropped inside the frame. Good for posts about rhythm, repetition, sequence. Generate by hand — do not use a pattern fill, because that can require a `<defs>` block.

### 5. The cut-out

A heavy shape filled in accent with a small negative space revealing a secondary glyph. Works for posts with a single strong metaphor.

## Anti-patterns

### Emoji or Unicode-as-icon

Characters like ✦, ◈, ❋ render inconsistently across fonts and OSes. Draw the shape as a `<polygon>` or `<path>` instead.

### Gradient fills via `<defs>`

Legal per contract but fragile — a flat accent on a neutral background reads cleaner at 260px. If you need depth, layer two opacities of the same hex.

### Small detailed illustration

Anything that needs to be zoomed in to appreciate. The card is a doorway, not a miniature. Keep shapes large.

### The post's title in the SVG

Already rendered below the tile by the template. Repeating it doubles the text mass and crowds the composition.

### Long text blocks

More than ~6 lines of text, or text smaller than `font-size="6"`, becomes illegible. Use shapes, not paragraphs.

### Accent as background wash

A 136×136 accent-filled rectangle behind everything is visually loud and competes with the shader wall. Keep the accent as ink, not paint.

## Typography notes

Permitted families (the gallery page loads these):

- `Cormorant Garamond, Georgia, serif` — display, italic, decorative. Sizes 60–110.
- `Inter, sans-serif` — captions, labels, small text. Sizes 7–14.
- `JetBrains Mono, monospace` — code, measurements, technical labels. Sizes 6–10.

Text anchor conventions:
- Large display text: `text-anchor="middle"`, `x="80"`.
- Labels above/below shapes: `text-anchor="middle"` with y offset.
- Seal-style blocks: `text-anchor="start"` at `x="24"` or similar, lines 14–16 apart.

## Neutral palette

Alongside the accent, these neutrals are safe:

- `#1a1a1e` — near-black body ink.
- `#8a8579` — warm grey for secondary strokes and ornament.
- `#f6f0e4` — parchment, for paper-like fills or negative cut-outs.

Do not use white (`#ffffff`) or pure black (`#000000`). The gallery background is dark and warm; full-saturation neutrals clash.
