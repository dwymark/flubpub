import re
import sys
import json
import shlex
import subprocess
import click
import httpx
from pathlib import Path
from bs4 import BeautifulSoup


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9-]+", "", text.lower().replace(" ", "-"))


IMG_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)]+\.(?:md|html))\)")

HTML_ASSET_ATTRS = [
    ("img", "src"),
    ("source", "src"),
    ("video", "src"),
    ("audio", "src"),
    ("link", "href"),
    ("script", "src"),
    ("iframe", "src"),
]

PAGE_SUFFIXES = {".md", ".html"}

REMOTE_SKIP_SCHEMES = ("http://", "https://", "//", "#", "mailto:", "data:", "javascript:")


def _strip_ref(ref: str) -> str:
    return ref.split("#", 1)[0].split("?", 1)[0]


def _is_local_ref(ref: str) -> bool:
    if not ref:
        return False
    return not ref.startswith(REMOTE_SKIP_SCHEMES)


def _scan_md(md_path: Path) -> tuple[list[Path], list[Path]]:
    content = md_path.read_text()
    base = md_path.parent
    assets, sub_pages = [], []
    for _, src in IMG_RE.findall(content):
        if not _is_local_ref(src):
            continue
        p = (base / _strip_ref(src)).resolve()
        if p.is_file():
            assets.append(p)
    for _, href in LINK_RE.findall(content):
        if not _is_local_ref(href):
            continue
        p = (base / _strip_ref(href)).resolve()
        if p.is_file():
            sub_pages.append(p)
    return assets, sub_pages


def _scan_html(html_path: Path) -> tuple[list[Path], list[Path]]:
    content = html_path.read_text()
    base = html_path.parent
    soup = BeautifulSoup(content, "html.parser")
    assets, sub_pages = [], []

    def add_local(ref: str, into: list[Path]) -> None:
        if not _is_local_ref(ref):
            return
        p = (base / _strip_ref(ref)).resolve()
        if p.is_file():
            into.append(p)

    for tag_name, attr in HTML_ASSET_ATTRS:
        for tag in soup.find_all(tag_name):
            add_local(tag.get(attr) or "", assets)

    for tag in soup.find_all("a"):
        href = tag.get("href") or ""
        if not _is_local_ref(href):
            continue
        p = (base / _strip_ref(href)).resolve()
        if not p.is_file():
            continue
        if p.suffix.lower() in PAGE_SUFFIXES:
            sub_pages.append(p)

    url_re = re.compile(r"url\(\s*['\"]?([^'\")]+)['\"]?\s*\)")
    for style in soup.find_all("style"):
        for m in url_re.findall(style.get_text()):
            add_local(m, assets)
    for tag in soup.find_all(style=True):
        for m in url_re.findall(tag["style"]):
            add_local(m, assets)

    return assets, sub_pages


def scan_local_refs(path: Path) -> tuple[list[Path], list[Path]]:
    suffix = path.suffix.lower()
    if suffix == ".md":
        return _scan_md(path)
    if suffix == ".html":
        return _scan_html(path)
    return [], []


def collect_all_refs(entry_path: Path) -> tuple[list[Path], list[Path]]:
    visited: set[Path] = set()
    all_assets: list[Path] = []
    all_sub_pages: list[Path] = []
    asset_set: set[Path] = set()
    sub_set: set[Path] = set()

    def _walk(p: Path):
        rp = p.resolve()
        if rp in visited:
            return
        visited.add(rp)
        assets, subs = scan_local_refs(p)
        for a in assets:
            if a not in asset_set:
                asset_set.add(a)
                all_assets.append(a)
        for s in subs:
            if s not in sub_set:
                sub_set.add(s)
                all_sub_pages.append(s)
            _walk(s)

    _walk(entry_path)
    entry_resolved = entry_path.resolve()
    all_sub_pages = [p for p in all_sub_pages if p != entry_resolved]
    return all_assets, all_sub_pages


def _rewrite_md(content: str, slug: str, asset_paths: list[Path], sub_paths: list[Path]) -> str:
    img_map = {p: f"/assets/{slug}/{p.name}" for p in asset_paths}
    link_map = {p: f"/{_slugify(p.stem)}/" for p in sub_paths}

    def replace_img(m):
        alt, src = m.group(1), m.group(2)
        for orig, rewritten in img_map.items():
            if orig.name == Path(_strip_ref(src)).name:
                return f"![{alt}]({rewritten})"
        return m.group(0)

    def replace_link(m):
        text, href = m.group(1), m.group(2)
        for orig, rewritten in link_map.items():
            if orig.name == Path(_strip_ref(href)).name:
                return f"[{text}]({rewritten})"
        return m.group(0)

    content = IMG_RE.sub(replace_img, content)
    content = LINK_RE.sub(replace_link, content)
    return content


def _rewrite_html(content: str, slug: str, asset_paths: list[Path], sub_paths: list[Path]) -> str:
    asset_by_name = {p.name: f"/assets/{slug}/{p.name}" for p in asset_paths}
    page_by_name = {p.name: f"/{_slugify(p.stem)}/" for p in sub_paths}

    soup = BeautifulSoup(content, "html.parser")
    replacements: dict[str, str] = {}

    for tag_name, attr in HTML_ASSET_ATTRS:
        for tag in soup.find_all(tag_name):
            ref = tag.get(attr) or ""
            if not _is_local_ref(ref):
                continue
            name = Path(_strip_ref(ref)).name
            if name in asset_by_name:
                replacements[ref] = asset_by_name[name]

    for tag in soup.find_all("a"):
        href = tag.get("href") or ""
        if not _is_local_ref(href):
            continue
        name = Path(_strip_ref(href)).name
        if name in page_by_name:
            replacements[href] = page_by_name[name]

    url_re = re.compile(r"url\(\s*(['\"]?)([^'\")]+)\1\s*\)")

    def _rewrite_url(m):
        quote, ref = m.group(1), m.group(2)
        if not _is_local_ref(ref):
            return m.group(0)
        name = Path(_strip_ref(ref)).name
        if name not in asset_by_name:
            return m.group(0)
        return f"url({quote}{asset_by_name[name]}{quote})"

    content = url_re.sub(_rewrite_url, content)

    # Prefer longer keys first to avoid partial-overlap rewrites.
    for old in sorted(replacements, key=len, reverse=True):
        new = replacements[old]
        content = content.replace(f'"{old}"', f'"{new}"')
        content = content.replace(f"'{old}'", f"'{new}'")
    return content


def rewrite_refs(content: str, slug: str, asset_paths: list[Path], sub_paths: list[Path],
                 mode: str = "md") -> str:
    if mode == "html":
        return _rewrite_html(content, slug, asset_paths, sub_paths)
    return _rewrite_md(content, slug, asset_paths, sub_paths)


REMOTE_FLUBPUB_DIR = "/opt/flubpub"
REMOTE_TMP_PREFIX = "/tmp/flubpub-upload-"


def _ssh_run(remote: str, cmd: str) -> subprocess.CompletedProcess:
    result = subprocess.run(["ssh", remote, cmd], capture_output=True, text=True)
    if result.returncode != 0:
        click.echo(f"SSH error: {result.stderr.strip()}", err=True)
        sys.exit(1)
    return result


def _scp_to(remote: str, local_path: Path, remote_path: str):
    result = subprocess.run(
        ["scp", str(local_path), f"{remote}:{remote_path}"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        click.echo(f"SCP error: {result.stderr.strip()}", err=True)
        sys.exit(1)


def _remote_cleanup(remote: str):
    _ssh_run(remote, f"rm -f {REMOTE_TMP_PREFIX}*")


def _remote_flubpub(remote: str, args: str):
    """Run a flubpub CLI command on the remote and print output."""
    cmd = f'PATH="$HOME/.local/bin:$PATH" && cd {REMOTE_FLUBPUB_DIR} && uv run flubpub {args}'
    result = _ssh_run(remote, cmd)
    if result.stdout:
        click.echo(result.stdout.strip())


def _upload_file_and_refs(remote: str, file_path: Path):
    """SCP a file (and its local refs if .md/.html) to the remote tmp dir."""
    _scp_to(remote, file_path, f"{REMOTE_TMP_PREFIX}{file_path.name}")
    if file_path.suffix.lower() in (".md", ".html"):
        assets, sub_pages = collect_all_refs(file_path)
        for ref in assets + sub_pages:
            _scp_to(remote, ref, f"{REMOTE_TMP_PREFIX}{ref.name}")


@click.group()
@click.option("--server", default="http://localhost:8000", show_default=True, help="Server base URL")
@click.option("--remote", default=None, help="SSH remote (e.g. root@host). Bypasses HTTP API.")
@click.pass_context
def cli(ctx, server, remote):
    ctx.ensure_object(dict)
    ctx.obj["server"] = server
    ctx.obj["remote"] = remote


@cli.command()
@click.argument("file_path")
@click.option("--title", default=None, help="Page title")
@click.option("--slug", default=None, help="URL slug")
@click.option("--theme", default=None, help="Theme name (geocities, academic, hacker, angelfire, web-ring)")
@click.option("--color-scheme", default=None, help="Color scheme (clean, neon, midnight, terminal, starfield, parchment)")
@click.pass_context
def push(ctx, file_path, title, slug, theme, color_scheme):
    """Push a file to the server as a published page."""
    path = Path(file_path)
    content = path.read_text()

    if not title:
        title = path.stem.replace("-", " ").replace("_", " ").title()

    remote = ctx.obj.get("remote")
    if remote:
        _upload_file_and_refs(remote, path)
        args = f"push {shlex.quote(REMOTE_TMP_PREFIX + path.name)} --title {shlex.quote(title)}"
        if slug:
            args += f" --slug {shlex.quote(slug)}"
        if theme:
            args += f" --theme {shlex.quote(theme)}"
        if color_scheme:
            args += f" --color-scheme {shlex.quote(color_scheme)}"
        _remote_flubpub(remote, args)
        _remote_cleanup(remote)
        return

    suffix = path.suffix.lower()
    if suffix == ".md":
        main_content_type = "markdown"
    elif suffix == ".html" and theme:
        main_content_type = "html"
    elif suffix == ".html":
        main_content_type = "html_raw"
    else:
        main_content_type = "html"

    page_slug = slug or _slugify(title)
    assets, sub_pages = [], []

    if suffix in (".md", ".html"):
        assets, sub_pages = collect_all_refs(path)
        if assets or sub_pages:
            click.echo("Local references found:")
            if assets:
                click.echo("  Assets:")
                for a in assets:
                    click.echo(f"    ./{a.relative_to(path.parent.resolve())}")
            if sub_pages:
                click.echo("  Linked pages:")
                for s in sub_pages:
                    click.echo(f"    ./{s.relative_to(path.parent.resolve())}")
            click.echo()
            click.confirm("These files will be uploaded. Continue?", abort=True)

    server = ctx.obj["server"]
    with httpx.Client() as client:
        for asset in assets:
            with open(asset, "rb") as f:
                resp = client.post(
                    f"{server}/api/assets/{page_slug}",
                    files={"file": (asset.name, f)},
                )
            if not resp.is_success:
                click.echo(f"Error uploading {asset.name}: {resp.text}", err=True)
                sys.exit(1)
            click.echo(f"Uploaded asset: {asset.name}")

        for sub in sub_pages:
            sub_title = sub.stem.replace("-", " ").replace("_", " ").title()
            sub_slug = _slugify(sub.stem)
            sub_content = sub.read_text()
            sub_suffix = sub.suffix.lower()
            sub_mode = "html" if sub_suffix == ".html" else "md"
            sub_ct = "html_raw" if sub_suffix == ".html" else "markdown"

            sub_assets, sub_links = scan_local_refs(sub)
            for asset in sub_assets:
                with open(asset, "rb") as f:
                    resp = client.post(
                        f"{server}/api/assets/{sub_slug}",
                        files={"file": (asset.name, f)},
                    )
                if not resp.is_success:
                    click.echo(f"Error uploading {asset.name}: {resp.text}", err=True)
                    sys.exit(1)
                click.echo(f"Uploaded asset: {asset.name} (for {sub_slug})")
            sub_content = rewrite_refs(sub_content, sub_slug, sub_assets, sub_links, mode=sub_mode)
            resp = client.post(
                f"{server}/api/pages",
                json={
                    "title": sub_title,
                    "content": sub_content,
                    "slug": sub_slug,
                    "content_type": sub_ct,
                },
            )
            if not resp.is_success:
                click.echo(f"Error pushing {sub.name}: {resp.text}", err=True)
                sys.exit(1)
            click.echo(f"Pushed linked page: {sub_slug}")

        if assets or sub_pages:
            main_mode = "html" if suffix == ".html" else "md"
            content = rewrite_refs(content, page_slug, assets, sub_pages, mode=main_mode)

        body = {"title": title, "content": content, "content_type": main_content_type}
        if slug:
            body["slug"] = slug
        if theme:
            body["theme"] = theme
        if color_scheme:
            body["color_scheme"] = color_scheme

        resp = client.post(f"{server}/api/pages", json=body)

    if resp.is_success:
        data = resp.json()
        click.echo(f"Published: {data['title']}")
        click.echo(data["url"])
    else:
        click.echo(f"Error: {resp.text}", err=True)
        sys.exit(1)


@cli.command(name="list")
@click.pass_context
def list_pages(ctx):
    """List published pages."""
    remote = ctx.obj.get("remote")
    if remote:
        _remote_flubpub(remote, "list")
        return

    with httpx.Client() as client:
        resp = client.get(f"{ctx.obj['server']}/api/pages")

    if not resp.is_success:
        click.echo(f"Error: {resp.text}", err=True)
        sys.exit(1)

    pages = resp.json()
    if not pages:
        click.echo("No pages published yet.")
        return

    col_w = (20, 30, 12, 12)
    click.echo(f"{'SLUG':<{col_w[0]}}{'TITLE':<{col_w[1]}}{'CREATED':<{col_w[2]}}{'UPDATED':<{col_w[3]}}")
    click.echo("-" * sum(col_w))
    for p in pages:
        created = p["created_at"][:10]
        updated = p["updated_at"][:10]
        updated_col = f"{updated}*" if updated != created else ""
        click.echo(f"{p['slug']:<{col_w[0]}}{p['title']:<{col_w[1]}}{created:<{col_w[2]}}{updated_col:<{col_w[3]}}")


@cli.command()
@click.argument("slug")
@click.pass_context
def get(ctx, slug):
    """Get full details of a published page by slug."""
    remote = ctx.obj.get("remote")
    if remote:
        _remote_flubpub(remote, f"get {shlex.quote(slug)}")
        return

    with httpx.Client() as client:
        resp = client.get(f"{ctx.obj['server']}/api/pages/{slug}")

    if not resp.is_success:
        click.echo(f"Error: {resp.text}", err=True)
        sys.exit(1)

    d = resp.json()
    click.echo(f"Title: {d['title']}")
    click.echo(f"Slug: {d['slug']}")
    click.echo(f"Created: {d['created_at']}")
    click.echo(f"Updated: {d['updated_at']}")
    click.echo(f"URL: {d['url']}")
    click.echo(f"Content-Type: {d['content_type']}")
    click.echo("---")
    click.echo(d["content"])


@cli.command()
@click.argument("slug")
@click.argument("file_path")
@click.option("--title", default=None, help="New page title")
@click.option("--theme", default=None, help="Theme name (geocities, academic, hacker, angelfire, web-ring)")
@click.option("--color-scheme", default=None, help="Color scheme (clean, neon, midnight, terminal, starfield, parchment)")
@click.pass_context
def revise(ctx, slug, file_path, title, theme, color_scheme):
    """Update an existing page with new content."""
    path = Path(file_path)

    remote = ctx.obj.get("remote")
    if remote:
        _upload_file_and_refs(remote, path)
        args = f"revise {shlex.quote(slug)} {shlex.quote(REMOTE_TMP_PREFIX + path.name)}"
        if title:
            args += f" --title {shlex.quote(title)}"
        if theme:
            args += f" --theme {shlex.quote(theme)}"
        if color_scheme:
            args += f" --color-scheme {shlex.quote(color_scheme)}"
        _remote_flubpub(remote, args)
        _remote_cleanup(remote)
        return

    content = path.read_text()
    suffix = path.suffix.lower()
    if suffix == ".md":
        content_type = "markdown"
    elif suffix == ".html" and theme:
        content_type = "html"
    elif suffix == ".html":
        content_type = "html_raw"
    else:
        content_type = "html"

    body = {"content": content, "content_type": content_type}
    if title:
        body["title"] = title
    if theme:
        body["theme"] = theme
    if color_scheme:
        body["color_scheme"] = color_scheme

    with httpx.Client() as client:
        resp = client.put(f"{ctx.obj['server']}/api/pages/{slug}", json=body)

    if resp.is_success:
        data = resp.json()
        click.echo(f"Revised: {data['title']}")
        click.echo(data["url"])
    else:
        click.echo(f"Error: {resp.text}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("slug")
@click.pass_context
def delete(ctx, slug):
    """Delete a published page by slug."""
    remote = ctx.obj.get("remote")
    if remote:
        _remote_flubpub(remote, f"delete {shlex.quote(slug)}")
        return

    with httpx.Client() as client:
        resp = client.delete(f"{ctx.obj['server']}/api/pages/{slug}")

    if resp.is_success:
        click.echo(f"Deleted: {slug}")
    else:
        click.echo(f"Error: {resp.text}", err=True)
        sys.exit(1)


INDEX_ASSETS_SLUG = "flubpub-index"


@cli.command(name="set-index")
@click.argument("file_path")
@click.pass_context
def set_index(ctx, file_path):
    """Install a custom HTML file as the site index.

    Scans the file for local assets (imgs, css, js, fonts, url() refs), uploads
    them to /assets/flubpub-index/, and rewrites paths. A <script type=
    "application/json" id="flubpub-pages"></script> tag in the file is filled
    with the current pages list at every rebuild.
    """
    path = Path(file_path)
    if path.suffix.lower() != ".html":
        click.echo("Index must be an .html file", err=True)
        sys.exit(1)

    remote = ctx.obj.get("remote")
    if remote:
        _upload_file_and_refs(remote, path)
        args = f"set-index {shlex.quote(REMOTE_TMP_PREFIX + path.name)}"
        _remote_flubpub(remote, args)
        _remote_cleanup(remote)
        return

    content = path.read_text()
    assets, sub_pages = scan_local_refs(path)
    if sub_pages:
        click.echo("Note: <a href> links to local .md/.html are ignored for the index.")

    if assets:
        click.echo("Local assets found:")
        for a in assets:
            click.echo(f"  ./{a.relative_to(path.parent.resolve())}")
        click.echo()
        click.confirm("These files will be uploaded. Continue?", abort=True)

    server = ctx.obj["server"]
    with httpx.Client() as client:
        for asset in assets:
            with open(asset, "rb") as f:
                resp = client.post(
                    f"{server}/api/assets/{INDEX_ASSETS_SLUG}",
                    files={"file": (asset.name, f)},
                )
            if not resp.is_success:
                click.echo(f"Error uploading {asset.name}: {resp.text}", err=True)
                sys.exit(1)
            click.echo(f"Uploaded asset: {asset.name}")

        if assets:
            content = rewrite_refs(content, INDEX_ASSETS_SLUG, assets, [], mode="html")

        resp = client.post(f"{server}/api/index", json={"content": content})

    if resp.is_success:
        click.echo("Custom index installed.")
    else:
        click.echo(f"Error: {resp.text}", err=True)
        sys.exit(1)


@cli.command(name="unset-index")
@click.pass_context
def unset_index(ctx):
    """Remove the custom index and restore the default."""
    remote = ctx.obj.get("remote")
    if remote:
        _remote_flubpub(remote, "unset-index")
        return

    with httpx.Client() as client:
        resp = client.delete(f"{ctx.obj['server']}/api/index")

    if resp.is_success:
        click.echo("Custom index removed.")
    else:
        click.echo(f"Error: {resp.text}", err=True)
        sys.exit(1)


@cli.command()
@click.option("--host", default="0.0.0.0", show_default=True, help="Bind host")
@click.option("--port", default=8000, show_default=True, help="Bind port")
def serve(host, port):
    """Start the flubpub server."""
    import uvicorn
    uvicorn.run("flubpub.server:app", host=host, port=port)
