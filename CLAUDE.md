# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

flubpub is a personal web publishing tool — like `gh gist` but for web pages. A CLI pushes content to a FastAPI server, which writes markdown files into an 11ty site and triggers a static rebuild. The result is a chronological index of published pages.

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

# Point CLI at production (HTTP API)
uv run flubpub --server http://danielwymark.com push page.html

# Point CLI at production (SSH, no HTTP API needed)
uv run flubpub --remote root@danielwymark.com push page.html
uv run flubpub --remote root@danielwymark.com list

# Build the 11ty site manually
cd site && npx @11ty/eleventy

# Deploy to production VPS
REMOTE_HOST=danielwymark.com bash deploy/deploy.sh
```

## Architecture

**Data flow:** CLI → POST /api/pages → server writes page file to `site/src/pages/` → server runs `npx @11ty/eleventy` in `site/` → static HTML appears in `site/_site/` → nginx serves `_site/` directly, proxies `/api/` and `/health` to uvicorn.

**Python package** (`src/flubpub/`):
- `cli.py` — Click CLI (push, list, get, revise, delete, serve), uses httpx sync client. Scans .md files for local image/link references and uploads them. Supports `--remote user@host` for SSH-based access (scp+ssh, no HTTP API needed).
- `server.py` — FastAPI app; full CRUD (POST/GET/PUT/DELETE), Jinja2 theme rendering, color scheme injection, asset upload, triggers 11ty rebuilds, mounts `_site/` as static files
- `models.py` — Pydantic models: PageCreate, PageUpdate, PageMeta, PageResponse, PageDetail
- `colors.py` — Named color schemes (clean, neon, midnight, terminal, starfield, parchment) as CSS custom property dicts. Default scheme mapping per theme.
- `themes/` — Jinja2 HTML templates using CSS custom properties for colors (6 themes: default, geocities, academic, hacker, angelfire, web-ring). Any color scheme can be paired with any theme.

**Static site** (`site/`): 11ty project. `eleventy.config.js` defines a `pages` collection from `src/pages/*.md` and `*.html` sorted newest-first. `src/index.njk` renders the chronological list. Assets in `src/assets/` are passed through.

**Page storage:** Each page is either a `.md` file (unthemed, rendered by 11ty through base.njk) or a `.html` file (themed, Jinja2-rendered with `layout: false`) in `site/src/pages/`. Metadata lives in `data/pages.json`. Assets are stored in `site/src/assets/{slug}/`.

**Deploy** (`deploy/`): systemd unit runs uvicorn as `flubpub` user; nginx reverse-proxies API and serves static files; `deploy.sh` builds locally, rsyncs, and sets up the remote.

## Production

- Deployed to `danielwymark.com` (DigitalOcean VPS, Ubuntu)
- Service: `systemctl status flubpub`
- Logs: `journalctl -u flubpub`
- nginx config: `/etc/nginx/sites-enabled/flubpub`
- Data on server: `/opt/flubpub/`
