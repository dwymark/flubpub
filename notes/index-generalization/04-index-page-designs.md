# Index Page Designs — Seven Diverse Concepts

Each concept follows the same brief: **one strong design idea** plus **at most
two understated eye-candy moves**. Minimalistic, never gimmicky. Each is a
separate Jinja template under `templates/<name>/`. Each consumes the data
contract from `02-nested-index-pages.md` and an optional payload shaper from
`03-wider-variety.md`.

The existing `gallery` template stays as-is and is the eighth concept (the
one we don't need to design). New ones below.

---

## 1. Quiet List

**Design idea.** A radical counterpoint to the gallery: just titles. Italic
serif, plenty of vertical air, hairline rules. It's the "all whitespace" mode
— content prevails by being almost the only thing on the page. Inspired by
Tufte's *layering and separation* (ch03) read maximally — the visual weight
budget goes to one place.

**Layout.** Single column, max-width 640px, centered. Each post is one line:

```
2026 · Apr 18    The Fisher–Frobenius Coincidence       ·math ·geometry
```

Three columns (date / title / tags) flowing together as one visual line,
separated by tiny mid-dots. Hairline rule between entries (1px,
`rgba(255,255,255,0.08)`).

**Eye candy moves.**

- **One accent dot** per entry, drawn in the post's `tile.accent` color, at
  the very left margin. The whole rest of the page is monochrome, so the
  dot reads as a tiny color-coded category mark.
- **Hover reveals excerpt**: a one-line excerpt slides in *underneath* the
  title in a slightly smaller weight. No transform on the title itself.
  Animation: 200ms ease.

**Why pleasant.** The page does almost nothing, so the *act of finding a
post* is the page's whole job. Reads fast on mobile. Honors `prefers-reduced-
motion`.

**Data needs.** `title`, `slug`, `created_at`. Optional: `tile.accent`,
`tags`, `excerpt`.

**Shaper.** `flat` (default).

---

## 2. Timeline

**Design idea.** Spatial encoding of time itself. Posts are pinned to a
vertical line at their actual date — gaps in posting *show* as gaps in the
visual. Inspired by Tufte ch06 (*narratives of space and time*) and the
mermaid timeline diagram, distilled to the essentials.

**Layout.** A vertical line down the center, ~2px, hairline. Years are
labeled in italic serif at the line, like grave-markers. Each post is a tiny
horizontal stem coming off the line (alternating left/right) ending in the
post title. Stem length is uniform; *what changes is the vertical position*,
which is proportional to the time delta between adjacent posts.

```
            2026 ─┤
                  │── Post C — 2026-04-22
       2026-04-18 ─── Post B
                  │
                  │
                  ├── Post A — 2026-04-09
            2025 ─┤
```

The vertical scale is one per visible post, so on long sites this becomes a
sparse but readable map of when one wrote.

**Eye candy moves.**

- **Tiny colored bullet** at the stem-line junction, again the post's
  `tile.accent`. Color is the only saturation in the page.
- **Decade backdrop**: the area between two year markers gets a 0.05-opacity
  fill, alternating between two values, so eras read as soft bands.

**Why pleasant.** Proportional time is genuinely informative — you see your
own creative cadence at a glance. The eye lands on dense areas without any
labeling needed.

**Data needs.** `title`, `slug`, `created_at`. Optional: `tile.accent`,
`tags`.

**Shaper.** `grouped` with `group_by: year`. Within a year, sort by date asc
or desc.

---

## 3. Voronoi Map

**Design idea.** Posts as Voronoi cells. Each post is a "site"; its territory
is the set of points closer to it than to any other post. Inspired by BCKO
ch7 (Voronoi as the post-office trading-area model) and shaders ch12.
Using **d3-delaunay** for the geometry — ~30 KB JS, computes Voronoi over a
few hundred points in milliseconds.

**Layout.** Full-page (or full-section) SVG with one polygon per post. Each
polygon is rendered as a thin-stroked outline with a sliver of the post's
`tile.accent` color (low opacity) tinting its interior. Each post's title is
typeset *inside* its cell at the cell's centroid, in a small uniform serif.

Site (post) positions come from a shaper:

- **`voronoi_sites_random`**: deterministic by `hash(slug)` → (x, y) over a
  Halton sequence. Stable across rebuilds.
- **`voronoi_sites_temporal`**: posts laid out radially from page center
  outward by recency — old posts at the rim, newest near center. Angle by
  hash to spread.
- **`voronoi_sites_clustered`**: tag-similarity spring layout (force-directed)
  computed once at rebuild time with a tiny iterative routine.

The cell boundaries come from `d3.Delaunay.from(points).voronoi(extent)`.

**Eye candy moves.**

- **Hover highlight**: hovered cell's polygon fills to its full accent color
  at low opacity (~0.15) and the title scales by 1.05. Adjacent cells dim
  ~10%.
- **Lloyd relaxation animation on first load**: sites start at hash positions
  and move 8 frames toward their cell centroids, settling into their final
  layout. Slow, ~600ms total. Honors `prefers-reduced-motion` (skip).

**Why pleasant.** Territorial layout reads as organic but is fully
deterministic. Each post owns a region, and the size of that region naturally
reflects its position relative to neighbors.

**Data needs.** `title`, `slug`, `url`. Optional: `tile.accent`, `tags`.

**Shaper.** `voronoi_sites_*` (one of three). Adds `_x` and `_y` floats to
each page in the payload.

---

## 4. Constellation

**Design idea.** Posts as points in a star field. Position is derived from
slug hash (so each post has a fixed "place" in the night sky). Brightness
encodes recency. Inspired by shaders ch10 (deterministic hash) and the
non-uniform clustering of geometry/quadtree.

**Layout.** Dark background. SVG circles scattered over the canvas at
positions determined by:

```js
// for each post, deterministic 2D position from slug hash
const x = (hash(slug, 'x') / 0xffffffff) * width
const y = (hash(slug, 'y') / 0xffffffff) * height
```

Circle radius `r = clamp(1, 4, 1 + (recencyDays < 30 ? 3 : recencyDays < 365 ? 2 : 1))`.

The post's title sits in tiny mono sans-serif beside its star, hidden by
default (only the star is visible). Hovering lifts the title to full
opacity.

To avoid clumping, run a **single pass** of mutual repulsion: any two stars
within `r1+r2+8px` push each other apart by half the overlap. One pass is
enough at our densities and stays deterministic.

**Eye candy moves.**

- **Faint connecting lines** between any two stars that share at least one
  tag. Stroke `rgba(255,255,255,0.05)`. Reads as constellations.
- **2-axis parallax on scroll**: the star field translates ~0.2× the scroll
  delta, with a deeper-back layer of static "background stars" (purely
  decorative, hash-positioned dots) translating ~0.05×. No infinite scroll —
  the page is one screen.

**Why pleasant.** Each post has a *home* on the page that's stable across
visits — visitors learn where their favorites live. Tag-edges create a
discoverable secondary layer.

**Data needs.** `title`, `slug`, `created_at`, `url`. Optional: `tags`.

**Shaper.** `flat`; the JS does the positioning.

---

## 5. Topographic

**Design idea.** A site-wide fBm topographic-map backdrop. Posts are placed
as labeled markers on the "terrain." Reuses the gallery's shader expertise —
fBm with domain warping (shaders ch11/ch13) — but renders **isolines** rather
than a colored field. Inspired by escaping flatland (Tufte ch01) — one
deterministic field gives every post a unique elevation.

**Layout.** Behind: a static SVG of contour lines computed from fBm of a
fixed seed. Foreground: post markers placed at hash-derived (x, y), each
showing a tiny dot + small italic label.

**Marker style.** Looks like a benchmark on a survey map: small triangle
with `▲` glyph, post title in 11px italic above. Hover scales text up.

**Eye candy moves.**

- **Subtle scroll motion**: contour lines drift slowly diagonally (using the
  scroll-motion technique from `/style web tilings`) at ~5 px/sec, so the
  map feels alive without being distracting. Honors reduced motion.
- **Hover reveals "elevation" digit**: a tiny "↑42" appears next to the
  marker, where 42 is `floor(fbm(x,y) * 100)`. Decorative — gives the page a
  hint of dimension.

**Why pleasant.** The topographic-map metaphor naturally supports
"exploration" — you scroll around looking for posts. Density variation in the
contours is visually interesting without being noisy. Pairs especially well
with mathematical or geographic content.

**Data needs.** `title`, `slug`, `url`. Optional: `tags`.

**Shaper.** `flat`. Position derived from `hash(slug)` at the template; fBm
contour lines are precomputed at rebuild time and inlined as a static SVG
path string.

**Implementation note.** Contour-line generation: a **marching squares** pass
on a 200×120 fBm grid yields polylines. Compute server-side at rebuild time;
emit as an inline `<svg><path d="..."/></svg>`. This is ~50 lines of python.
No shader runtime cost; no GPU dependency.

---

## 6. Mindmap

**Design idea.** Hierarchical fan. Site root at the center, each top-level
parent a major branch, children further out. Inspired by mermaid's mindmap
syntax distilled to its essence — *radial hierarchy*. Requires the optional
`parent: <slug>` metadata from `02-nested-index-pages.md`.

**Layout.** SVG, centered. Polar coordinates: root at (0,0), level-1 children
at radius 180px around the root, level-2 at radius 320px, etc. Branches are
hand-curved Bézier arcs from parent to child. Each node is a small text
label, no boxes.

If a post has no parent, it appears as a level-1 child of the synthetic
"root" page (i.e., orphans cluster around the center).

**Eye candy moves.**

- **Branch curvature deviates slightly per branch**, derived from
  `hash(slug)`, so the diagram looks hand-drawn rather than mechanical.
- **Hover-fade-and-grow**: hovered node grows by 1.1×; nodes that aren't
  ancestors or descendants fade to 0.4 opacity. Reveals the lineage.

**Why pleasant.** For a site with a strong topical hierarchy, this is the
single most readable view. Visitors see structure at a glance. Quietly
educational about how the site is organized.

**Data needs.** `title`, `slug`, `url`, `parent` (optional).

**Shaper.** `topic_tree`: turns the flat list into `{slug: …, children: […]}`
nested structure based on `parent` fields. ~20 lines.

**Caveat.** Falls apart at scale (>~80 nodes) — at that point the radial
layout gets cluttered. Useful for sites with deliberately-small structured
content.

---

## 7. Marginalia

**Design idea.** A reading view. Each post is a *paragraph* of excerpt
running down the page; the title sits in the margin to the left, locked to
its excerpt. Inspired by the *micro/macro* principle (Tufte ch02, NeXTSTEP
inspector panel pattern) — the page is content-rich at the macro and per-
entry-rich at the micro. Inspired aesthetically by Tufte's own
margin-note-heavy book design.

**Layout.** Two columns:

- Left margin: 200px, contains pinned post titles in italic serif, right-
  aligned, in a slightly smaller weight.
- Right body: 600px max, contains the post excerpt as flowing prose. Soft
  hairline rule (~24px height blank) between entries.

Each title-excerpt pair is sticky so hovering scrolls don't lose the
correspondence. On narrow viewports (<800px), title and excerpt stack
vertically.

**Eye candy moves.**

- **Drop cap on each excerpt**: the first letter of each post's excerpt is
  rendered in 36px Cormorant italic in the post's `tile.accent` color. A
  decades-old book convention used sparingly.
- **Margin asterisk** at the end of each excerpt that links to the full
  post. Tiny, mid-dot grey, single character: `*`.

**Why pleasant.** This is the index that reads like a book itself. Visitors
can absorb the whole site without clicking — only follow up with the
asterisk if a paragraph hooks them. Privileges the *writing* over the
*post-as-object*.

**Data needs.** `title`, `slug`, `url`, **`excerpt`** (required). The
excerpt is a new field — the first 240 chars of the post's content,
populated at push time. We add a small extractor in the server (markdown
strip + truncate at sentence boundary).

**Shaper.** `flat` with optional limit.

---

## Summary

| # | Name | Key idea | Eye candy | Special data |
|---|---|---|---|---|
| 1 | quiet-list | total minimalism | accent dot, hover-reveal excerpt | excerpt (optional) |
| 2 | timeline | proportional time spacing | accent bullet, era-band backdrop | created_at |
| 3 | voronoi-map | territorial cells | hover lift, Lloyd relax on load | x,y via shaper |
| 4 | constellation | hash-positioned stars | tag-edges, parallax scroll | tags (optional) |
| 5 | topographic | fBm contour-line backdrop | scroll drift, elevation digit | hash position |
| 6 | mindmap | radial hierarchy | hand-drawn curves, lineage hover | parent |
| 7 | marginalia | excerpt-first reading view | drop cap, margin asterisk | excerpt (required) |

All seven plus the existing gallery (= 8 templates) cover a wide spectrum:
list / timeline / map / sky / terrain / tree / book / grid. Each occupies a
different mental model. Each consumes the same data contract.
