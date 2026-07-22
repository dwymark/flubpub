# audit danielwymark.com for pages leaked by past deploys

Until the deploy.sh fix (git: "deploy.sh: never rsync server-managed instance content"), `deploy.sh` rsynced the local dev install's `site/src/pages` and `site/src/assets` to the box with no `--delete` and no exclusion, so every deploy could publish local dev content onto the live site. bj was hit this session — ~15 stray dev pages plus orphaned asset dirs, all cleaned. dwm was **not** audited and may carry the same residue from earlier deploys.

The fix prevents recurrence. It does not clean what earlier deploys already pushed. This task is the one-time cleanup for dwm.

**Do.** On the box, diff `/opt/flubpub-dwm/data/pages.json` slugs against the page dirs under `/opt/flubpub-dwm/site/_site/` and the files in `/opt/flubpub-dwm/site/src/pages/`. Anything present in `_site`/`src/pages` but absent from `pages.json` is a leak candidate. Cross-check against the local repo's `site/src/pages` (the leak source) to confirm. Purge stray `src/pages` files, stray `_site/<slug>/` dirs, and orphaned `src/assets`/`_site/assets` dirs, keeping only `pages.json`-backed content plus `assets`, `fonts`, and `index.html`.

**Trap (differs from bj).** dwm pages are not all self-contained — several legitimately reference `/assets/`. Grep each kept page for `/assets/` and confirm which asset dirs are live before removing any. Do not blanket-empty `src/assets` the way bj allowed.

**Falsifier.** Every `_site` page dir maps to a `pages.json` slug; probing a known stray slug returns 404; every kept page's asset references still resolve.
