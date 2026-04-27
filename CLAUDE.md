# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

flubpub is a personal web publishing tool — like `gh gist` but for web pages. A CLI pushes content to a FastAPI server, which writes markdown files into an 11ty site and triggers a static rebuild. The result is a chronological index of published pages.

A single host can run multiple **side-by-side installs**, one per domain, each with its own data, port, systemd instance, and nginx site. Disambiguation is via a **sites registry** at `~/.config/flubpub/sites.toml`; the Python package itself contains zero references to any specific site.

## Commands

```bash
# Run the server locally
uv run flubpub serve

# Push a page (server must be running)
uv run flubpub push mypage.html --title "My Page"
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
    --server-name danielwymark.com --port 8001 --default
uv run flubpub sites add bj  root@danielwymark.com:/opt/flubpub-bj \
    --server-name bijectivity.net --port 8002

uv run flubpub sites list                    # inspect; * marks default
uv run flubpub sites set-default bj          # change default
uv run flubpub sites remove old-site

# Then publish via --site (or rely on the default):
uv run flubpub --site dwm push page.html --title "About"
uv run flubpub --site bj  list
uv run flubpub push page.md                  # uses default site
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

## Architecture

**Data flow:** CLI → POST /api/pages → server writes page file to `site/src/pages/` → server runs `npx @11ty/eleventy` in `site/` → static HTML appears in `site/_site/` → nginx serves `_site/` directly, proxies `/api/` and `/health` to uvicorn.

**Resolution order for `--remote`/`--site`:** `--remote SPEC` (raw, wins) > `--site KEY` > `FLUBPUB_SITE` env > registry `[default]` > local HTTP (`--server`, default `http://localhost:8000`). When a site is in play, the CLI also injects `--server http://localhost:<port>` into the remote-side `uv run flubpub` invocation, since each install's uvicorn binds a unique port.

**Python package** (`src/flubpub/`):
- `cli.py` — Click CLI (push, list, get, revise, delete, serve, deploy, sites group). Uses httpx for HTTP, scp+ssh for `--remote`. Scans .md/.html files for local image/link references and uploads them. The `--site KEY` flag resolves a remote spec from `~/.config/flubpub/sites.toml`. The package has zero hardcoded site keys.
- `server.py` — FastAPI app; full CRUD (POST/GET/PUT/DELETE), Jinja2 theme rendering, color scheme injection, asset upload, triggers 11ty rebuilds, mounts `_site/` as static files. Reads `FLUBPUB_DATA_DIR` and `FLUBPUB_SITE_DIR` from env (set per-instance by systemd).
- `models.py` — Pydantic models: PageCreate, PageUpdate, PageMeta, PageResponse, PageDetail
- `colors.py` — Named color schemes (clean, neon, midnight, terminal, starfield, parchment) as CSS custom property dicts. Default scheme mapping per theme.
- `themes/` — Jinja2 HTML templates using CSS custom properties for colors (6 themes: default, geocities, academic, hacker, angelfire, web-ring). Any color scheme can be paired with any theme.

**Static site** (`site/`): 11ty project. `eleventy.config.js` defines a `pages` collection from `src/pages/*.md` and `*.html` sorted newest-first. `src/index.njk` renders the chronological list. Assets in `src/assets/` are passed through.

**Page storage:** Each page is either a `.md` file (unthemed, rendered by 11ty through base.njk) or a `.html` file (themed, Jinja2-rendered with `layout: false`) in `site/src/pages/`. Metadata lives in `data/pages.json`. Assets are stored in `site/src/assets/{slug}/`. Each install owns its own `data/` and `site/`, so two installs can host pages with the same slug without conflict.

**Deploy** (`deploy/`):
- `flubpub@.service` — templated systemd unit. `%i` substitutes the site key into `WorkingDirectory=/opt/flubpub-%i`, `EnvironmentFile=/opt/flubpub-%i/instance.env`. Each instance reads `FLUBPUB_PORT`, `FLUBPUB_DATA_DIR`, `FLUBPUB_SITE_DIR` from its own `instance.env`. One unit file on disk; many instances enabled (`flubpub@dwm`, `flubpub@bj`, …).
- `nginx-site.conf.template` — three substitution points (`__SERVER_NAME__`, `__INSTALL_ROOT__`, `__PORT__`) rendered per-site by sed during deploy. Result lands at `/etc/nginx/sites-available/flubpub-<key>` with a sites-enabled symlink.
- `deploy.sh` — requires `SITE`, `REMOTE_HOST`, `SERVER_NAME`, `PORT`. Builds wheel locally, rsyncs, writes `instance.env` on the remote, installs the templated unit, renders the nginx site, reloads both daemons. Idempotent. Honors `REMOTE_DIR` override (set by `flubpub deploy`), `REMOTE_USER` (defaults `root`), and `ETC` (defaults `/etc`; only used by tests).

**Test harness** (`tests/`): A `FakeRemote` context manager shims `ssh`/`scp`/`rsync` (and optionally system commands like `systemctl`/`nginx`/`npm`/`uv`) onto `PATH`, rewrites a configurable install-prefix to a temp directory, and writes a JSONL transcript of every call. `smoke_test_remote.py`, `smoke_test_sites.py`, and `smoke_test_deploy.py` exercise the routing, registry, and full deploy pipeline without touching a real VPS. Run with `uv run python3 tests/smoke_test_<name>.py`.

## Production

- Deployed to `danielwymark.com` (DigitalOcean VPS, Ubuntu)
- Two installs: `/opt/flubpub-dwm/` (port 8001, served at `danielwymark.com`) and `/opt/flubpub-bj/` (port 8002, served at `bijectivity.net`)
- Services: `systemctl status flubpub@dwm flubpub@bj`
- Logs: `journalctl -u flubpub@dwm` / `journalctl -u flubpub@bj`
- nginx configs: `/etc/nginx/sites-enabled/flubpub-dwm` and `/etc/nginx/sites-enabled/flubpub-bj` (each with explicit `server_name`, no catch-all)
- The legacy single-instance setup (`flubpub.service`, `/opt/flubpub/`, `/etc/nginx/sites-enabled/flubpub`) is disabled but still on disk; remove if you want.
- Adding a third site: pick key + free port + hostname, point DNS at the VPS, run `flubpub sites add … --server-name … --port …`, then `flubpub deploy --site …`. No source modification.
