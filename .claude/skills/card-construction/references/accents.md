# Accent palette

Six accent keys are authorized. The hex values mirror `ACCENTS` in `templates/gallery-tiles.js`. Use the key in `tile.accent`; use the hex inside SVG fills/strokes.

| Key    | Hex       | Swatch mood                                    | When to pick                                                         |
|--------|-----------|-----------------------------------------------|----------------------------------------------------------------------|
| `rust` | `#c44a2a` | Warm, oxidized, Sienna-like. High chroma.     | Recipes, memoir, warmth, craft, things that rust.                    |
| `teal` | `#3a6e6e` | Muted Prussian-green. Cool, contemplative.    | Essays, systems thinking, code, cartography, water.                  |
| `sand` | `#b08a55` | Desert gold, parchment ink on linen.          | Field notes, travel, history, geography, ephemera.                    |
| `ink`  | `#2b2b2e` | Near-black with a cool cast. Graphite.        | Obituaries, monographs, typography, strict formal work, code listings.|
| `moss` | `#5b6b3a` | Olive undergrowth. Slow, botanical.           | Nature, walks, slow observation, long reads, the pastoral.           |
| `plum` | `#6b3a5b` | Purple-brown, velvet-at-dusk.                 | Poetry, marginalia, dreams, the obscure, the personal.               |

## Pairing heuristics

- If the post is about code, `teal` and `ink` are the defaults; `rust` reads as "craft of coding", `sand` reads as "archival dig into old code".
- If the post is an essay, `teal`, `moss`, or `plum` tend to suit the genre; avoid `rust` unless the subject is explicitly warm.
- If the post is a field note, `sand` is almost always right; `moss` works if the field is botanical.
- If the post is a list, the accent should come from the list's subject, not from "list-ness".

Three concepts should not all share an accent. If two feel inevitable, make the third deliberately contrarian — the contrast is what makes phase 4 useful.

## Never do this

- Do not invent new keys (no `#coral`, `#indigo`, etc.). The renderer only knows these six.
- Do not use the accent hex for large flat fills — it overpowers the tile. Use it for strokes, small solid shapes, and text.
- Do not mix two accent hexes in one SVG. Pick one; use neutrals (`#1a1a1e`, `#8a8579`, `#f6f0e4`) for secondary ink.
