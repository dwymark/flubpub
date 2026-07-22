# add content/bj/_manifest.toml so `flubpub --site bj sync` works

The content/ reconcile command (`flubpub --site KEY sync`) reads `content/<KEY>/_manifest.toml` to learn which entry is the index (`index = "..."`); every other top-level entry is treated as a page. bj has no manifest, so `sync` cannot run for it — the drift-reconcile safety net that dwm has is missing for bj.

**Do.** Add `content/bj/_manifest.toml` with `index = "home.html"` (the front page). The atlas (`realized-arrangements-of-six-circles.html`) is then picked up as a page automatically. Mirror the shape of `content/dwm/_manifest.toml`, which is deliberately minimal.

Points at: CLAUDE.md "Content source of truth"; `content/dwm/_manifest.toml` for the reference shape.
