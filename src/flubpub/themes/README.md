# Themes

A **theme** is one Jinja2 template in this directory (`<name>.html`). It wraps a
page's content into a complete HTML document. A theme never hard-codes colors:
it styles everything against CSS custom properties (`--bg`, `--fg`, `--accent`,
…). The actual colors come from a **color scheme** (`flubpub/colors.py`), a dict
of those properties the server injects into `<head>` at render time.

## How a theme is chosen and colored

A page selects a theme with `theme: <name>` in its frontmatter. The colors come
from the page's `color_scheme:` if it names one, otherwise from the theme's
default in `DEFAULT_SCHEMES` (eponymous by convention — theme `harbor` defaults
to scheme `harbor`). Themes and schemes are otherwise independent: any scheme
can pair with any theme.

`available_themes()` lists a template per `*.html` file here, so adding a theme
is just adding a file.

## Two kinds of theme

- **Standalone** themes carry their own full HTML and CSS in one file.
- **Papered** themes share `_papered/_base.html` and differ only by a wallpaper
  and a palette. The base supplies the layout: a centered reading card floating
  over a fixed, tiled wallpaper, plus typography, list, and table styles. (It
  also suppresses the breadcrumb and colophon on the reserved root slug.)

A papered theme is a thin child of the base. It overrides one or two blocks:

- `{% block wallpaper %}` — an inline SVG `<pattern>` (256×256, `userSpaceOnUse`)
  filling a full-window rect. The pattern's colors are `var(--pattern-fg)` and
  `var(--pattern-accent)`; stroke width is `var(--pattern-stroke)`. So the
  wallpaper recolors itself from the page's scheme.
- `{% block extra_styles %}` (optional) — small palette or opacity nudges.

Because the wallpaper reads its colors from custom properties, a papered scheme
must carry the papered contract on top of the standard keys: `--card-bg`,
`--ink-light`, `--rule`, `--pattern-fg`, and `--pattern-accent`.

## Adding a papered theme

1. **Palette.** Design a scheme by color theory — value carries hierarchy, one
   accent does emphasis, and it should survive a grayscale check. Add it to
   `COLOR_SCHEMES` in `flubpub/colors.py` with the full papered contract.
2. **Wallpaper.** Pick a tiling. The `/style web tilings` catalog ships verified
   wallpaper-group SVG patterns. Lift a tile's drawing into a `{% block
   wallpaper %}` `<pattern>`, rewriting the tile's color vars to
   `var(--pattern-fg)` / `var(--pattern-accent)` so the scheme drives them.
3. **Template.** Write `<name>.html` extending `_papered/_base.html` with that
   wallpaper block.
4. **Default.** Map the theme to its scheme in `DEFAULT_SCHEMES` (eponymous).

The page then just says `theme: <name>`, and the paired scheme follows unless it
names a different `color_scheme`.
