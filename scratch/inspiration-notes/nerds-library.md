# Nerds Library Inspiration — Notes for index page designs

## Resource 1: Book of Shaders, ch12 Cellular Noise (Voronoi)

- **Distance fields = "for each pixel, distance to closest feature point"** — generalizable mental model for any spatial layout where elements have an implicit "territory."
- **Tile-based optimization**: divide space into cells, only check current cell + 8 neighbors → O(1) per pixel. Exact same trick works for laying out cards on a page: bin pages into a grid, each card only "looks at" siblings in adjacent cells.
- **Voronoi metaphor for index pages**: treat each post as a "site"; mouse position becomes a 9th moving site; the cell under the cursor highlights or expands. Reads as territorial/organic rather than gridded.
- **F1 vs F2 vs F2-F1 textures**: same input, different distance metric, totally different look. Suggests *one* spatial data structure can drive multiple visual modes for the same index.
- **Cell-space precision trick** (Quilez): drop integer parts away — only fractional cell coords matter. For an "infinite scrolling" index this is how you keep precision on large IDs.
- **"Each point grows until it meets another point"** — animation idiom: tiles "settle" into their voronoi shape on page load. Mirrors organic growth in nature.
- **Stippling / cracks / metaballs / tissue** — all derive from cellular noise with different post-processing. A backdrop generator for the entire site theme.
- **Practical:** Voronoi cells make a great hover-state highlight (irregular polygon clip-path) instead of rectangular bounding boxes.

## Resource 2: Book of Shaders, ch9 Patterns (Truchet, brick, grid)

- **Truchet tiles**: a *single* design element rotated/flipped per cell yields infinite non-repeating designs. Excellent for an index "constellation" view where each post produces one Truchet tile keyed to its slug hash.
- **Brick offset trick**: `mod(row, 2.0) * 0.5` = staggered rows. Quick way to break up a boring grid without abandoning grid layout.
- **`fract(st * N)` / `floor(st * N)`** = "tile space + tile index." This is the canonical recipe; for an index page we'd use post slug → hash → tile coordinate.
- **Grid + per-cell variation**: the formula is "grid provides framework; variation provides interest." Aim for understated variation — Scottish tartan, Greek meanders, I-Ching hexagrams as inspiration.
- **Animation hooks**: animate offset with time, animate even rows left/odd rows right. Gentle motion without being gimmicky.
- **Implication for design**: the more rigid the grid, the more freedom you have for *micro*-variation per cell (rotation, color hue shift, single decorative glyph).

## Resource 3: BCKO ch7 Voronoi diagrams

- **Voronoi assignment model = "every customer goes to the nearest store."** For an index page: every pixel "belongs" to the nearest post; clicking anywhere in a cell opens that post.
- **Each Voronoi cell is convex** — guaranteed clean polygonal regions, no overlaps. Trivial to render with SVG `<polygon>` or CSS `clip-path: polygon(...)`.
- **Theorem 7.3**: a Voronoi diagram of n sites has ≤ 2n-5 vertices and ≤ 3n-6 edges. So even with hundreds of posts, the rendered diagram stays linear in size.
- **Largest empty circle characterization**: useful for a "nearest neighbors" sidebar — for a hovered post, find the 3 sites whose joint empty circle defines its Voronoi vertex.
- **Plane sweep / Fortune's algorithm**: O(n log n). Plenty fast for our use case but we don't need to implement — JS libraries (d3-delaunay) compute Voronoi in ms for thousands of points.
- **Application angle**: use it the BCKO way — as a "trading area" map. Cluster posts by tag; sites are tag centroids; trading areas = "regions of the site where this topic dominates."
- **Sites need not be in 2D**: the construction generalizes to "Voronoi-like" partitions over arbitrary metrics. Could partition posts by (date, length) or (theme, color_scheme) and visualize the partition.

## Resource 4: BCKO ch14 Quadtrees (non-uniform mesh)

- **Quadtree = recursive 4-way subdivision**: root square → 4 quadrants → repeat where detail is needed. For an index, "detail" = where many posts cluster in time or topic.
- **Non-uniform meshes**: fine near features, coarse far from features. Translates directly to a temporal index — fine-grained near recent posts, coarse around old archived stuff.
- **Steiner points**: extra vertices added beyond the input set to fix triangle quality. Index analog: insert "synthetic" entries (separators, era headers) to keep visual cells well-shaped.
- **Conforming mesh property**: triangles never have a vertex of another triangle on an edge interior. Translation: cells should align cleanly; no half-overlapping rectangles.
- **Quadtree gives natural hierarchy**: zoom in = descend a level. Index page can be panned/zoomed; deeper zoom reveals more posts within a region.
- **Implementation simplicity**: quadtree subdivision is a few dozen lines of code. d3-quadtree exists. Could drive a "starfield" view where stars cluster densely in active periods.
- **Mesh generation insight**: quality (well-shaped triangles) > raw count. For the index, this translates to: don't pack tightly — leave whitespace. Quality of layout > number of posts crammed in.

## Cross-cutting design principles distilled

- **Tile-then-vary**: fix a strict grid; vary one or two parameters per cell. Holds tension between order and surprise.
- **Distance-driven layout**: a single field (distance to feature points, time delta, tag similarity) can drive multiple visual treatments.
- **Convex regions over rectangles**: Voronoi cells are organic but well-defined — feel curated, not algorithmic.
- **Hierarchical detail**: quadtree-style "zoom in for more" is more interesting than infinite linear scroll.
- **Cell space, not domain space**: design at the local scale (per-tile, per-cell) and the global emerges; resists precision and performance issues.
