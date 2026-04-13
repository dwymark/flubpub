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
uv run flubpub list
uv run flubpub delete my-slug

# Point CLI at production
uv run flubpub --server http://danielwymark.com push page.html

# Build the 11ty site manually
cd site && npx @11ty/eleventy

# Deploy to production VPS
REMOTE_USER=root REMOTE_HOST=danielwymark.com bash deploy/deploy.sh
```

## Architecture

**Data flow:** CLI → POST /api/pages → server writes `site/src/pages/{slug}.md` with YAML frontmatter → server runs `npx @11ty/eleventy` in `site/` → static HTML appears in `site/_site/` → nginx serves `_site/` directly, proxies `/api/` and `/health` to uvicorn.

**Python package** (`src/flubpub/`):
- `cli.py` — Click CLI, uses httpx sync client to talk to the server
- `server.py` — FastAPI app; page CRUD, triggers 11ty rebuilds, mounts `_site/` as static files (via lifespan so the directory exists first)
- `models.py` — Pydantic models: PageCreate, PageMeta, PageResponse

**Static site** (`site/`): 11ty project. `eleventy.config.js` defines a `pages` collection from `src/pages/*.md` sorted newest-first. `src/index.njk` renders the chronological list.

**Page storage:** Each page is a markdown file in `site/src/pages/` (consumed by 11ty) plus an entry in `data/pages.json` (metadata index used by the API). Both are authoritative — the markdown file is the source of truth for content, `pages.json` for metadata.

**Deploy** (`deploy/`): systemd unit runs uvicorn as `flubpub` user; nginx reverse-proxies API and serves static files; `deploy.sh` builds locally, rsyncs, and sets up the remote.

## Production

- Deployed to `danielwymark.com` (DigitalOcean VPS, Ubuntu)
- Service: `systemctl status flubpub`
- Logs: `journalctl -u flubpub`
- nginx config: `/etc/nginx/sites-enabled/flubpub`
- Data on server: `/opt/flubpub/`
