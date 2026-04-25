# /style Inspiration — Notes for index page designs

## Resource 1: /style visual dashboard (Tufte + NeXTSTEP)

### Tufte's principles applied to index pages

- **Escape flatland**: a list of titles is flat; a chronologically-spaced timeline with size and density variations adds dimensions on the same 2D surface.
- **Micro/macro**: design a single page that reads at *both* zoom levels — overview density at the macro scale, individual title legibility at the micro. "To clarify, add detail."
- **Layering and separation**: stratify by visual weight, not by boxes/rules. Avoid "1+1=3" — heavy gridlines + heavy borders = optical noise.
- **Small multiples**: a fleet of N posts as a grid of identical framelets differing only in data. "Constancy of design puts the emphasis on changes in data." This is *exactly* the gallery tile concept; double down on it.
- **Color as label/measure**: reserve saturated color for state that matters (e.g. theme, color_scheme, recency). Default chrome should be neutral.
- **Narrative of space and time** (ch06): use spatial layout to encode temporal sequence, giving random access to the whole story. *Critical insight*: a chronological index already does this, but the layout itself can encode the time axis spatially (timeline view, year columns, decade clusters).

### NeXTSTEP control taxonomy applied

- **Action vs state controls**: an index card is a *state display* (it shows what a post is). Don't disguise it as a button.
- **Direct manipulation > modal tools**: filtering should happen inline (toggling tags directly modifies the visible set), not in a separate modal/wizard.
- **User in control**: respect order/filter selections; don't auto-rearrange under them.
- **Density without modes** (cross-source theme 7): prefer layering + inspector panels over tabs/wizards. *For nested indexes*: don't tab between "all posts" and "topic X" — show topic X's posts inline as a layer over the global index.

### Anti-patterns to avoid for indexes

- **Tabs that hide live state** — operator must click to see if there's something new.
- **Brand-color chrome** — spends color budget before data arrives.
- **Hover-required readouts** — a post's title/date/tags must be readable at rest, not on hover.
- **Popover clouds** — occlude the very thing they're elaborating.
- **Unique widgets per device** — destroys small-multiples comparison. Translation: every post tile should *look the same* and differ only in content.

### Cross-source themes especially relevant

- **Theme 1: Layering vs. panels**: density on the main surface (the index); drill-in lives in inspector panels (sidebar showing hovered post detail).
- **Theme 2: Small multiples as control grids**: gallery tiles ARE this pattern.
- **Theme 5: Narrative as direct manipulation**: timelines should be scrubbable; the histogram of posts-per-week IS the filter control.

---

## Resource 2: /style web tilings subskill

### What's in the catalog

- **39 patterns** across 17 wallpaper groups + 5 non-period families (Voronoi, Delaunay, Truchet, Penrose, girih).
- Themable through 5 CSS custom properties: `--tiling-bg`, `--tiling-fg`, `--tiling-accent-1`, `--tiling-accent-2`, `--tiling-opacity`.
- Numerically verified for group symmetry (so they're guaranteed to tile cleanly).

### Selection guidance distilled

- **Quietly textured background**: `p1`, `p2`, `pm`. Use these for index page backdrops where content dominates.
- **Decorative border / divider**: `pmm`, `cmm` with small period.
- **Centerpiece motif**: `p4m`, `p6m`, or one of the non-period patterns.
- **Subtle technical-paper background**: low-opacity `p1` or `pmm`.
- For our use case (understated index pages): low-opacity `p1`, `pm`, or `voronoi` are the natural fits.

### Animation primitive (highly reusable)

- **Scroll-motion implementation** is documented and minimal:
  - SVG → data URI → `background-image` of a fixed-position layer.
  - `background-repeat: repeat`, fixed `background-size = tilePeriod`.
  - `requestAnimationFrame` accumulator; modulo by `tilePeriod` for seamless looping.
  - dt clamp at 0.05s prevents teleport on tab-blur resume.
  - `prefers-reduced-motion` gate.
- ~20 lines of JS. Trivially droppable into any flubpub index theme.

### Theming caveat

- `var(--tiling-*)` doesn't resolve through `background-image: url(...)` — must inline SVG OR pre-bake colors server-side. flubpub's Jinja2 server-side render is the natural choice for pre-baking.

### Index page applications

- **Wallpaper backdrop** for a "vintage notebook" index style.
- **Voronoi non-period** as the *layout primitive*, not just background — d3-delaunay generates a real Voronoi over post centroids.
- **Truchet tiles** keyed to slug hash → each post gets a unique 4-orientation tile rendered next to it as a tiny glyph.
- **Penrose / girih** for an "archive vault" feel — denser, more decorative, deliberately laggy reading pace for a "deep cuts" view.

### Cross-skill: tilings → BCKO

- The tilings subskill explicitly references the `nerds-library/geometry` library for the underlying CG primitives. Already extracted; consistent vocabulary.

---

## Cross-cutting design principles distilled

- **Reserve color budget**: default to monochrome chrome; spend saturation on signal (recency, theme).
- **Small multiples are cheap variety**: same widget × varied data = both legibility AND distinctiveness.
- **Time as space**: don't list dates — *position* posts by date.
- **No modes**: avoid tabs/filters that hide other state. Layered density wins.
- **Static patterns + light motion**: a wallpaper backdrop with slow scroll is more elegant than per-element animation.
- **Inspector panel pattern**: hovering a post tile updates a sidebar with its details, instead of expanding/collapsing the tile.
