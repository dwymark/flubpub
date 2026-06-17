# Strange Interlocutor hub — build system

The hub and its no-JS variants are generated, not hand-edited. The maintenance
surface is three things:

- `content.jsonl` — the canonical content (one JSON object per line: `meta`,
  `theme`, `piece`, `artifacts_meta`, `artifact`, `depiction`, `contrib`,
  `note`). Edit prose, links, glosses, and bylines here.
- `templates/hub.html.j2` — one Jinja template for every variant. Readable
  HTML/CSS/JS with the explanatory comments kept inline. `{% if js_hub %}`
  gates the canvas, chooser, deck, and the flock script; the content loops fill
  `#content`, which is both the deck's source and the no-JS reading column.
- `build.py` — wiring plus the per-variant background assets.

`assets/` holds the three baked backgrounds (base64): a settled flock
(`frozen-animated`), a gray-dithered flock (`frozen-retro`), and the p4
bird wallpaper SVG (`wallpaper`). Re-snapshot the first two from a
reduced-motion render if the flock changes.

## Regenerate

```bash
python3 content/dwm/_hub/build.py            # writes into content/dwm/
python3 content/dwm/_hub/build.py /tmp/out   # or somewhere else, for testing
```

This writes three self-contained `html_raw` pages:

| output | variant | notes |
| --- | --- | --- |
| `strange-interlocutor.html` | JS hub | deck + live chooser; no-JS fallback is the Animated stacked column |
| `strange-interlocutor-retro.html` | static Retro | stacked column over the gray flock, no JS |
| `strange-interlocutor-plain.html` | static Plain | stacked column over the bird wallpaper, no JS |

The three differ only in data: which background they carry, which theme link is
depressed, and which rendition the essay links point at. The roomy paged layout
of the JS deck is unchanged.

`_hub/` is metadata, not a page — the leading underscore keeps it out of the
deploy mirror, and per-file `push` never touches it.
