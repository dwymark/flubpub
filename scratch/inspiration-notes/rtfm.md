# /rtfm Inspiration — Notes for index page designs

## Resource 1: Mermaid mindmap diagram

- **Hierarchical visual organization** — single root concept with branches. Translates directly to: a "topic root" index page where the central concept = site name, and each category branches out.
- **Indent-driven hierarchy**: the syntax is just a text outline with indentation. For flubpub, *frontmatter* could specify a parent → indent in the rendered mindmap auto-derives.
- **Multiple node shapes** (square, rounded, circle, bang, cloud, hexagon) — could map post *type* (essay vs note vs sketch) to shape, giving zero-cost visual differentiation.
- **Markdown strings inside nodes** — bold, italic, soft-wrap. So a mindmap node can contain a brief preview of post title + date.
- **Tidy-tree layout** option for cleaner rendering at large fan-out.
- **Icons via `::icon(...)`**: requires site-admin font loading. flubpub could expose Font Awesome via the index page theme and let posts declare an icon in frontmatter.
- **Implementation simplicity**: ship Mermaid as `<script type="module">` from CDN; render into `<pre class="mermaid">` block. No build step, no framework dependency.
- **CAVEAT**: "experimental" — syntax may change. For a personal site this is fine; would not bet on it for production.
- **For an index page**: a "topic mindmap" is a unique navigation surface. User starts at root, drills into branches. Highly readable for sites with strong topical structure.

## Resource 2: Mermaid timeline diagram

- **Native chronological diagram type** — the index *is* a timeline if posts have dates. Mermaid renders this in 5 lines of declarative syntax.
- **`time period : event`** — multiple events per period. Multiple posts on same day cluster naturally.
- **Sections (ages)** group time periods — translates to "site eras." A flubpub site naturally has them: "early experiments," "post-redesign," etc., declared via frontmatter group.
- **Direction**: `LR` (default) or `TD`. For mobile-friendly index, `TD` is the obvious choice.
- **Color scheme automatic**: each section / time-period gets distinct color via `cScale0..11`. Good for sectioned index without manual styling.
- **`disableMulticolor`** option: monochrome timeline for understated aesthetic.
- **Themes**: base, forest, dark, default, neutral — themable to match site color scheme via existing flubpub `colors.py` infrastructure (override `cScale*` from CSS custom properties).
- **Grouping → site sub-index**: each "section" of the timeline could be a *separate index page* for that era — provides a natural hierarchy without committing to deep nesting.
- **Wrapping built-in**: long titles auto-wrap. Less manual work than custom CSS.

## Cross-cutting takeaways

- **Diagrams as indexes**: an index page need not be a list. Mermaid gives us mindmap, timeline, treemap, sankey, gantt, gitGraph, kanban — all of which are *spatial encodings of a collection*. Each tells a different story about the same set of posts.
- **Declarative source > imperative rendering**: a mermaid block is short, plain text, easy to generate from python. Server-side build can produce mermaid markup from `pages.json`.
- **CDN-loaded mermaid is ~free**: no build pipeline change. Single `<script>` tag.
- **Themes via CSS variables**: mermaid honors theme variables; same flubpub `--bg` / `--fg` / `--accent-1` could feed `cScale*` and `themeVariables.primaryColor`.
- **The "experimental" tag for mindmap/timeline** is the main constraint. Not blocker for personal site.
- **Index-page as one-of-many**: just like a post can pick a *theme*, an index page should pick a *layout type* (timeline, mindmap, gallery, list, treemap, …) — same pattern, generalized.
