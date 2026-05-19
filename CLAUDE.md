# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

flubpub is a personal web publishing tool — like `gh gist` but for web pages. A CLI pushes content to a FastAPI server, which writes markdown files into an 11ty site and triggers a static rebuild. The result is a chronological index of published pages.

A single host can run multiple **side-by-side installs**, one per domain, each with its own data, port, systemd instance, and nginx site. Disambiguation is via a **sites registry** at `~/.config/flubpub/sites.json` (plain JSON, read/written symmetrically — a pre-JSON `sites.toml` is converted once via the delete-after-use `migrate-sites-config.py` at the repo root, *not* a permanent CLI subcommand); the Python package itself contains zero references to any specific site.

## Local-vs-remote routing — read this first

⚠️ **`~/.config/flubpub/sites.json` has a `default` key.** When set, *every*
content command (`push`, `revise`, `list`, `get`, `delete`, `set-index`) that
doesn't specify `--site`, `--remote`, `--local`, or `FLUBPUB_SITE` silently
routes through SSH to that default site's production VPS. **This means a bare
`uv run flubpub push foo.md` against your local server is — by default — a
production push.**

**Always pass `--local` when testing against a local `flubpub serve`.** It
bypasses the sites registry entirely and targets `--server` (default
`http://localhost:8000`). It also overrides `--site`, `--remote`, and
`FLUBPUB_SITE` if any of them happen to be set in the environment.

```bash
# Local development — ALWAYS use --local
uv run flubpub --local push page.md
uv run flubpub --local list
uv run flubpub --local set-index home.md
```

The `--local` flag must come **before** the subcommand (it's a group-level
option). Not `flubpub push --local` (Click will reject it).

## Commands

```bash
# Run the server locally
uv run flubpub serve

# Push a page locally (server must be running)
uv run flubpub --local push mypage.html --title "My Page"
uv run flubpub push mypage.html --theme geocities  # themed page
uv run flubpub push mypage.html --theme hacker --color-scheme midnight  # theme + color scheme
uv run flubpub push doc.md  # auto-scans for local images/links
uv run flubpub list
uv run flubpub get my-slug
uv run flubpub revise my-slug updated-page.html --title "New Title" --theme hacker
uv run flubpub delete my-slug

# Build the 11ty site manually
cd site && npx @11ty/eleventy

# --- Multi-install: sites registry ---

# Configure once, with everything deploy needs:
uv run flubpub sites add dwm root@danielwymark.com:/opt/flubpub-dwm \
    --server-name danielwymark.com --port 8001 --default --email you@example.com
uv run flubpub sites add bj  root@danielwymark.com:/opt/flubpub-bj \
    --server-name bijectivity.net --port 8002
# or set "acme_email": "you@example.com" at the top of sites.json to apply
# the same address to every site

uv run flubpub sites list                    # inspect; * marks default
uv run flubpub sites set-default bj          # change default
uv run flubpub sites remove old-site
uv run flubpub sites set-content-root ~/flubpub  # anchor the SSOT (see below)
python3 migrate-sites-config.py              # one-off (repo root): sites.toml -> sites.json, then rm it

# Then publish via --site (or rely on the default). Every push/revise/
# set-index/delete also mirrors the bundle into content/<key>/ (the SSOT),
# so you can publish a draft from anywhere and the tree stays canonical:
uv run flubpub --site dwm push page.html --title "About"
uv run flubpub --site bj  list
uv run flubpub push page.md                  # uses default site
uv run flubpub --no-mirror --site dwm push page.md   # skip the content/ mirror
FLUBPUB_SITE=bj uv run flubpub list          # env-var override

# Raw escape hatches still work:
uv run flubpub --remote root@host:/opt/flubpub-bj push page.md
uv run flubpub --server http://localhost:8001 push page.html

# Deploy a configured site (reads everything from the registry):
uv run flubpub deploy --site dwm
uv run flubpub deploy                        # default site

# Bare deploy.sh still works as the underlying primitive:
SITE=dwm REMOTE_HOST=danielwymark.com SERVER_NAME=danielwymark.com PORT=8001 \
    bash deploy/deploy.sh
```

## Content source of truth

The `content/` directory is the version-controlled source of truth for every
page published to a flubpub site, and the CLI keeps it that way automatically.
Every `push`/`revise`/`set-index`/`delete` that resolves to a registry site
key mirrors the published bundle into `content/<key>/` (and `delete` removes
it). "Publish a draft from anywhere — `/tmp`, a scratchpad, wherever" is
**literally** true once you anchor the SSOT with `flubpub sites
set-content-root <repo>`: the mirror root then comes from the registry, not
from CWD, so the canonical tree updates no matter where you run flubpub.
Without that anchor it falls back to a CWD walk (nearest `.git`/`pyproject.toml`),
which only mirrors when you happen to be inside the repo. Layout is
partitioned by site key, mirroring the sites registry:

```
content/
  dwm/
    home.md
    <slug>.{md,html}        # a ref-free page lands flat
    <slug>/                 # a page with assets/sub-pages lands as a dir,
      <entry>.{md,html}     #   entry keeps its source filename,
      diagram.png           #   refs preserved relative to the entry
  bj/
    ...
```

Exactly one shape per slug — the mirror drops the opposite flat/dir form on
write, so the tree never carries a stale duplicate.

Mirroring is skipped for: `--local` (the local dev install is not the SSOT,
see below) and a raw `--remote` spec with no matching registry entry (the
escape hatch isn't registry-backed). Opt out per-invocation with
`--no-mirror` or globally with `FLUBPUB_NO_MIRROR=1`.

Not auto-mirrored: per-page `tile` metadata (produced by `/card-construction`,
not present in the markdown source) — see [`DWM.md`](./DWM.md) for the
deferred plan.

> **TODO / known invariant gap.** Because `tile` is not mirrored, the SSOT
> guarantee is "lossless rebuild-from-`content/` **modulo tiles**." For any
> site that actually uses the gallery layout, `content/` alone is *not*
> sufficient to reconstruct the site. Close this by committing a sanitized
> `content/<key>/tiles.json` on write (see `DWM.md`) before the gallery goes
> into production use; until then, state the claim with the "modulo tiles"
> qualifier wherever it's made.

Not source of truth: `site/src/pages/` and `data/pages.json` at the repo root.
Those belong to the local dev install (`flubpub serve`) and are rebuilt by
every local push.

If this repo ever goes public, `content/` is the directory to exfiltrate or
gitignore.

Per-site notes (vendored projects, tile-metadata plans, refresh recipes) live
in sibling docs at the repo root: see [`DWM.md`](./DWM.md) for the
danielwymark.com install.

## Architecture

**Data flow:** CLI → POST /api/pages → server writes page file to `site/src/pages/` → server runs `npx @11ty/eleventy` in `site/` → static HTML appears in `site/_site/` → nginx serves `_site/` directly and proxies only `/health` to uvicorn. **nginx does NOT proxy `/api/`** — the API is an unauthenticated mutation surface, uvicorn binds `127.0.0.1` only, and the CLI reaches it over SSH (running `flubpub` on the box against `http://localhost:PORT`) or locally via `--local`. Nothing public needs `/api/`.

**Resolution order for `--remote`/`--site`:** `--remote SPEC` (raw, wins) > `--site KEY` > `FLUBPUB_SITE` env > registry `[default]` > local HTTP (`--server`, default `http://localhost:8000`). When a site is in play, the CLI also injects `--server http://localhost:<port>` into the remote-side `uv run flubpub` invocation, since each install's uvicorn binds a unique port.

**Python package** (`src/flubpub/`):
- `cli.py` — Click CLI (push, list, get, revise, delete, serve, deploy, sites group). Uses httpx for HTTP, scp+ssh for `--remote`. Scans .md/.html files for local image/link references and uploads them. The `--site KEY` flag resolves a remote spec from `~/.config/flubpub/sites.json`. The package has zero hardcoded site keys. Registry I/O is symmetric JSON (`_load_sites_config`/`_save_sites_config`); the repo-root `migrate-sites-config.py` (a delete-after-use one-off, not a CLI subcommand) converts a legacy `sites.toml` once.
- **in-file SoT (#11):** for `.md` `push`/`revise`, any explicit CLI override (`--title/--slug/--theme/--color-scheme/--parent/--tag/--excerpt`) is written *into the source file's YAML frontmatter first* (`_apply_cli_overrides_to_md_file`), with a per-key diagnostic, then the now-canonical file is read and pushed. Frontmatter is authoritative; the CLI just keeps it honest. If the source isn't writable (e.g. read-only `/tmp`), it warns and pushes the merged values un-persisted.
- **content/ mirror-on-write:** `_resolve_remote` also returns the resolved registry key; `_should_mirror` gates on it (None for `--local` / unmatched raw `--remote` / `--no-mirror` / `FLUBPUB_NO_MIRROR`). After a successful remote `push`/`revise`/`set-index`, `_mirror_to_content` copies the bundle into `content/<key>/` via `_content_root()` — the registry's `content_root` (set by `sites set-content-root`) when present, else the nearest `.git`/`pyproject.toml` ancestor of CWD, else a notice; `delete` calls `_unmirror_from_content`. `_mirror_bundle_pairs` reuses `collect_all_refs` and the same relative-to-entry layout as `_upload_bundle_to_remote`: ref-free → flat `content/<key>/<slug>.<ext>`, otherwise a `content/<key>/<slug>/` dir. It writes the bundle first, then drops the opposite flat/dir form so a slug never carries both (copy-before-remove keeps a source that lived in the old shape safe); a file is never copied onto itself (`shutil.copy2` would raise `SameFileError`). Mirroring runs only in the remote branch, after `_remote_flubpub` (which `sys.exit`s on failure), so it never claims an unpublished page.
- **Remote upload shape:** `push`, `revise`, and `set-index` over `--remote` use `_upload_bundle_to_remote`, which scp's the entry file and its sibling assets/sub-pages into a fresh `/tmp/flubpub-upload-dir-<hex>/` on the remote, preserving each asset's path *relative to the entry file's directory* (subdir refs like `url("fonts/X.ttf")` keep their `fonts/` prefix; assets outside the entry's tree fall back to basename). The remote-side `flubpub` then re-scans the file in that dir, resolves relative refs (CSS/JS/images, .md links), uploads assets via the local HTTP API, and rewrites refs. Cleanup via `rm -rf /tmp/flubpub-upload-*`. (Don't collapse the bundle root into `/tmp/flubpub-upload-<basename>`; that breaks relative resolution on the remote and silently ships un-rewritten refs.) `click.confirm` prompts in `push`, `revise`, and `set-index` are gated on `sys.stdin.isatty()` so the inner remote invocation doesn't abort under non-interactive ssh.
- `server.py` — FastAPI app; full CRUD (POST/GET/PUT/DELETE), Jinja2 theme rendering, color scheme injection, asset upload, triggers 11ty rebuilds, mounts `_site/` as static files. Reads `FLUBPUB_DATA_DIR` and `FLUBPUB_SITE_DIR` from env (set per-instance by systemd). `upload_asset` reduces the client-controlled slug (`[a-z0-9-]+`) and filename (`Path(...).name`) to single safe path segments — no traversal escapes the assets tree even though the API is localhost-only.
- **One index model.** A "page-type index" is any `pages.json` entry with `content_type: index`. `resolve_index(content, content_type, body_index, *, force_index=False)` is the single place the "is this an index, in what form?" promotion rules live — called by `create_page`, `update_page`, and the `/api/index` adaptor; both write paths funnel through `_create_or_replace_page` (one persistence model). **The site front page is just the page-type index at the reserved slug `ROOT_INDEX_SLUG` ("index").** `set_custom_index` (`POST /api/index`) is thin sugar: classify with `force_index=True`, create/replace that entry. `inject_index_pages` is one loop; the root's *only* specialness is mechanical — its URL is `/`, so its injected output is written to `_site/index.html` (overwriting 11ty's `src/index.njk` build) and the routed `_site/index/` duplicate is removed. The pre-unification root store (`data/custom_index.html` + `custom_index_spec.json`, `_render_root_markdown`, the `inject_custom_index` alias) is **deleted**; `_sweep_legacy_root_index` drops those stale files on the next `set-index`/`unset-index` of an upgraded install. `unset-index` deletes the root entry so 11ty's default `index.njk` wins again. (`style_css` on a markdown root index is gone — themed roots go through the theme catalogue; un-themed roots render via 11ty `base.njk`.)
- `models.py` — Pydantic models: PageCreate, PageUpdate, PageMeta, PageResponse, PageDetail
- `colors.py` — Named color schemes (clean, neon, midnight, terminal, starfield, parchment) as CSS custom property dicts. Default scheme mapping per theme.
- `themes/` — Jinja2 HTML templates using CSS custom properties for colors (6 themes: default, geocities, academic, hacker, angelfire, web-ring). Any color scheme can be paired with any theme.

**Static site** (`site/`): 11ty project. `eleventy.config.js` defines a `pages` collection from `src/pages/*.md` and `*.html` sorted newest-first. `src/index.njk` renders the chronological list. Assets in `src/assets/` are passed through.

**Page storage:** Each page is either a `.md` file (unthemed, rendered by 11ty through base.njk) or a `.html` file (themed, Jinja2-rendered with `layout: false`) in `site/src/pages/`. Metadata lives in `data/pages.json`. Assets are stored in `site/src/assets/{slug}/`. Each install owns its own `data/` and `site/`, so two installs can host pages with the same slug without conflict.

**Deploy** (`deploy/`):
- `flubpub@.service` — templated systemd unit. `%i` substitutes the site key into `WorkingDirectory=/opt/flubpub-%i`, `EnvironmentFile=/opt/flubpub-%i/instance.env`. Each instance reads `FLUBPUB_PORT`, `FLUBPUB_DATA_DIR`, `FLUBPUB_SITE_DIR` from its own `instance.env`. One unit file on disk; many instances enabled (`flubpub@dwm`, `flubpub@bj`, …).
- `nginx-site.conf.template` — three substitution points (`__SERVER_NAME__`, `__INSTALL_ROOT__`, `__PORT__`) rendered per-site by sed during deploy. Result lands at `/etc/nginx/sites-available/flubpub-<key>` with a sites-enabled symlink.
- `deploy.sh` — requires `SITE`, `REMOTE_HOST`, `SERVER_NAME`, `PORT`. Builds wheel locally, rsyncs, writes `instance.env` on the remote, installs the templated unit, renders the nginx site, reloads both daemons. Idempotent. Honors `REMOTE_DIR` override (set by `flubpub deploy`), `REMOTE_USER` (defaults `root`), `ETC` (defaults `/etc`; only used by tests), and `EMAIL` (if set, runs `certbot --nginx -d $SERVER_NAME -m $EMAIL --redirect` after the HTTP config is reloaded; certbot installs its own renewal timer).
- **TLS:** Opt-in via `EMAIL`. The nginx template ships HTTP-only; `certbot --nginx` rewrites it on first run to add the 443 block and 80→443 redirect. On re-deploy, deploy.sh re-renders the HTTP-only config, then certbot re-applies its edits — net result is the same HTTPS config, with churn only during the deploy window. `flubpub deploy` resolves `EMAIL` from per-site `email`, top-level `acme_email`, or the `EMAIL` env var.

**Test harness** (`tests/`): A `FakeRemote` context manager shims `ssh`/`scp`/`rsync` (and optionally system commands like `systemctl`/`nginx`/`npm`/`uv`) onto `PATH`, rewrites a configurable install-prefix to a temp directory, and writes a JSONL transcript of every call. `smoke_test_remote.py`, `smoke_test_sites.py`, and `smoke_test_deploy.py` exercise the routing, registry, and full deploy pipeline without touching a real VPS. Run with `uv run python3 tests/smoke_test_<name>.py`.

## Production

- Deployed to `danielwymark.com` (DigitalOcean VPS, Ubuntu)
- Two installs: `/opt/flubpub-dwm/` (port 8001, served at `danielwymark.com`) and `/opt/flubpub-bj/` (port 8002, served at `bijectivity.net`)
- Both on HTTPS via Let's Encrypt; certs at `/etc/letsencrypt/live/{danielwymark.com,bijectivity.net}/`. Renewal handled by the `certbot.timer` systemd unit (preinstalled with the certbot package).
- Services: `systemctl status flubpub@dwm flubpub@bj`
- Logs: `journalctl -u flubpub@dwm` / `journalctl -u flubpub@bj`
- nginx configs: `/etc/nginx/sites-enabled/flubpub-dwm` and `/etc/nginx/sites-enabled/flubpub-bj` (each with explicit `server_name`, no catch-all)
- Legacy single-instance setup (`flubpub.service`, `/opt/flubpub/`, `/etc/nginx/sites-enabled/flubpub`): defunct. Reclaim it — `systemctl disable --now flubpub` and delete the unit, dir, and nginx site. (Not "remove if you want": leaving dead infra beside live infra is the exact carrying cost this codebase otherwise avoids.)
- **Pending security action:** the public-`/api/` lockdown ships in this branch but production isn't fixed until each live site is redeployed. Tracked by `deploy/TODO-dwm-api-lockdown.md` (a `.claude/settings.json` SessionStart hook nags every session until that file is `rm`'d). Run `flubpub deploy --site dwm && flubpub --site dwm set-index content/dwm/home.md` (and the same for `bj`) on a machine with the ssh key.
- Adding a third site: pick key + free port + hostname, point DNS at the VPS, run `flubpub sites add … --server-name … --port …`, then `flubpub deploy --site …`. No source modification.
