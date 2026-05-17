import os
import re
import sys
import json
import shlex
import shutil
import subprocess
import tempfile
import click
import httpx
import yaml
from pathlib import Path
from bs4 import BeautifulSoup
from jinja2 import Template


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


_MD_FM_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.DOTALL)


def _split_md_frontmatter(text: str) -> tuple[str, dict | None]:
    """Strip a leading `---…---` YAML block from a markdown string. Returns
    (body_without_frontmatter, parsed_dict_or_None)."""
    match = _MD_FM_RE.match(text)
    if not match:
        return text, None
    try:
        data = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        return text, None
    return text[match.end():], data if isinstance(data, dict) else None


def _merge_frontmatter(content: str, suffix: str, *,
                       title: str | None, theme: str | None,
                       color_scheme: str | None, parent: str | None,
                       tags: tuple, excerpt: str | None,
                       slug: str | None = None) -> dict:
    """For .md inputs, parse YAML frontmatter and merge into the supplied
    CLI-flag values — CLI flags always win. Returns a dict with the
    (possibly-stripped) content and the resolved fields. The `index` key,
    if present in the frontmatter, is lifted into a structured field the
    server promotes to a markdown-sourced index page."""
    out = {
        "content": content, "title": title, "theme": theme,
        "color_scheme": color_scheme, "parent": parent,
        "tags": tags, "excerpt": excerpt, "slug": slug, "index": None,
    }
    if suffix != ".md":
        return out
    body, fm = _split_md_frontmatter(content)
    if fm is None:
        return out
    out["content"] = body
    out["title"]        = title        or fm.get("title")
    out["theme"]        = theme        or fm.get("theme")
    out["color_scheme"] = color_scheme or fm.get("color_scheme")
    out["parent"]       = parent       or fm.get("parent")
    out["excerpt"]      = excerpt      or fm.get("excerpt")
    out["slug"]         = slug         or fm.get("slug")
    if not tags:
        fm_tags = fm.get("tags") or []
        if isinstance(fm_tags, list):
            out["tags"] = tuple(fm_tags)
    if isinstance(fm.get("index"), dict):
        out["index"] = fm["index"]
    return out


def _scan_md(md_path: Path) -> tuple[list[Path], list[Path]]:
    content = md_path.read_text()
    base = md_path.parent
    assets, sub_pages = [], []
    seen_assets: set[Path] = set()
    seen_subs: set[Path] = set()
    for _, src in IMG_RE.findall(content):
        if not _is_local_ref(src):
            continue
        p = (base / _strip_ref(src)).resolve()
        if p.is_file() and p not in seen_assets:
            seen_assets.add(p)
            assets.append(p)
    for _, href in LINK_RE.findall(content):
        if not _is_local_ref(href):
            continue
        p = (base / _strip_ref(href)).resolve()
        if p.is_file() and p not in seen_subs:
            seen_subs.add(p)
            sub_pages.append(p)
    # Markdown frequently embeds raw HTML (e.g. <link rel=stylesheet>,
    # <script src=...>, <iframe>); markdown-it passes those through unchanged,
    # so we also scan HTML asset/page refs from the same content.
    html_assets, html_subs = _scan_html(md_path)
    for p in html_assets:
        if p not in seen_assets:
            seen_assets.add(p)
            assets.append(p)
    for p in html_subs:
        if p not in seen_subs:
            seen_subs.add(p)
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
    # Raw HTML embedded in markdown (e.g. <script src=...>, <link href=...>)
    # also needs its refs rewritten — markdown-it passes those through.
    content = _rewrite_html_refs_inline(content, slug, asset_paths, sub_paths)
    return content


def _rewrite_html_refs_inline(content: str, slug: str,
                              asset_paths: list[Path], sub_paths: list[Path]) -> str:
    """Light-touch ref rewrite for raw HTML inside a markdown body. Unlike
    _rewrite_html it doesn't reparse the document — it just substitutes
    occurrences of each ref string in attribute values, scoped by basename."""
    asset_by_name = {p.name: f"/assets/{slug}/{p.name}" for p in asset_paths}
    page_by_name = {p.name: f"/{_slugify(p.stem)}/" for p in sub_paths}
    if not asset_by_name and not page_by_name:
        return content
    pairs: list[tuple[str, str]] = []
    attr_re = re.compile(r'''(href|src)=(["'])([^"']+)\2''')
    for m in attr_re.finditer(content):
        ref = m.group(3)
        if not _is_local_ref(ref):
            continue
        name = Path(_strip_ref(ref)).name
        if name in asset_by_name:
            pairs.append((m.group(0), f'{m.group(1)}={m.group(2)}{asset_by_name[name]}{m.group(2)}'))
        elif name in page_by_name:
            pairs.append((m.group(0), f'{m.group(1)}={m.group(2)}{page_by_name[name]}{m.group(2)}'))
    for old, new in pairs:
        content = content.replace(old, new, 1)
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


DEFAULT_REMOTE_DIR = "/opt/flubpub"
REMOTE_TMP_PREFIX = "/tmp/flubpub-upload-"


def _parse_remote(spec: str) -> tuple[str, str]:
    """Split `user@host[:/abs/path]` into (host, install_dir).

    The path component is optional and must be absolute when present;
    otherwise the legacy default is applied.
    """
    if ":" in spec:
        host, _, path = spec.rpartition(":")
        if path.startswith("/"):
            return host, path
    return spec, DEFAULT_REMOTE_DIR


SITES_CONFIG_PATH = Path.home() / ".config" / "flubpub" / "sites.toml"


def _load_sites_config() -> dict:
    """Read the sites registry. Returns {} if absent or unreadable."""
    if not SITES_CONFIG_PATH.is_file():
        return {}
    import tomllib
    try:
        return tomllib.loads(SITES_CONFIG_PATH.read_text())
    except tomllib.TOMLDecodeError as e:
        click.echo(f"Warning: could not parse {SITES_CONFIG_PATH}: {e}", err=True)
        return {}


def _resolve_remote(remote: str | None, site: str | None) -> tuple[str | None, int | None]:
    """Resolve --remote / --site / default-from-config / FLUBPUB_SITE env into
    a (remote_spec, port) tuple. Returns (None, None) for local-HTTP mode.
    The port is taken from the registry when --site is used (or default)."""
    if remote:
        return remote, None
    site = site or os.environ.get("FLUBPUB_SITE")
    cfg = _load_sites_config()
    if not site:
        site = cfg.get("default")
    if not site:
        return None, None
    sites = cfg.get("sites") or {}
    entry = sites.get(site)
    if not entry:
        click.echo(
            f"Site '{site}' not found in {SITES_CONFIG_PATH}. "
            f"Configured sites: {', '.join(sites) or '(none)'}",
            err=True,
        )
        sys.exit(1)
    spec = entry.get("remote") if isinstance(entry, dict) else None
    if not spec:
        click.echo(f"Site '{site}' has no 'remote' key.", err=True)
        sys.exit(1)
    port = entry.get("port") if isinstance(entry, dict) else None
    return spec, port


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
    _ssh_run(remote, f"rm -rf {REMOTE_TMP_PREFIX}*")


def _remote_flubpub(remote: str, remote_dir: str, args: str,
                    remote_port: int | None = None):
    """Run a flubpub CLI command on the remote and print output.

    When `remote_port` is given, the remote CLI is told to talk to that port
    instead of the default 8000 — required for multi-install hosts where
    each site's uvicorn binds a different port."""
    server_flag = f"--server http://localhost:{remote_port} " if remote_port else ""
    cmd = (
        f'PATH="$HOME/.local/bin:$PATH" && cd {shlex.quote(remote_dir)} '
        f'&& uv run flubpub {server_flag}{args}'
    )
    result = _ssh_run(remote, cmd)
    if result.stdout:
        click.echo(result.stdout.strip())


def _upload_bundle_to_remote(remote: str, file_path: Path) -> str:
    """SCP a file plus its sibling assets into a fresh remote tempdir,
    preserving each asset's path relative to the entry file's directory so
    the remote-side scan resolves relative refs (including subdir refs like
    url("fonts/X.ttf")) correctly. Assets outside the entry's tree fall back
    to basename. Returns the remote path of the entry file. The dir matches
    the flubpub-upload-* glob, so existing cleanup catches it."""
    import uuid
    rdir = f"{REMOTE_TMP_PREFIX}dir-{uuid.uuid4().hex[:8]}"
    _ssh_run(remote, f"mkdir -p {shlex.quote(rdir)}")
    _scp_to(remote, file_path, f"{rdir}/{file_path.name}")
    if file_path.suffix.lower() not in (".md", ".html"):
        return f"{rdir}/{file_path.name}"
    base = file_path.parent.resolve()
    assets, sub_pages = collect_all_refs(file_path)
    rel_paths: list[tuple[Path, str]] = []
    for ref in assets + sub_pages:
        try:
            rel = ref.resolve().relative_to(base).as_posix()
        except ValueError:
            rel = ref.name
        rel_paths.append((ref, rel))
    parent_dirs = {Path(rel).parent.as_posix() for _, rel in rel_paths
                   if Path(rel).parent.as_posix() not in ("", ".")}
    for sub in sorted(parent_dirs):
        _ssh_run(remote, f"mkdir -p {shlex.quote(f'{rdir}/{sub}')}")
    for ref, rel in rel_paths:
        _scp_to(remote, ref, f"{rdir}/{rel}")
    return f"{rdir}/{file_path.name}"


@click.group()
@click.option("--server", default="http://localhost:8000", show_default=True, help="Server base URL")
@click.option("--remote", default=None,
              help="SSH remote (e.g. root@host[:/abs/path]). Overrides --site.")
@click.option("--site", default=None,
              help="Site key from ~/.config/flubpub/sites.toml. "
                   "Falls back to FLUBPUB_SITE env or [default].")
@click.option("--local", "force_local", is_flag=True, default=False,
              help="Bypass the sites registry entirely and target --server "
                   "(default http://localhost:8000). USE WHEN TESTING LOCALLY "
                   "to avoid silently pushing through SSH to a production "
                   "site listed as `default` in ~/.config/flubpub/sites.toml.")
@click.pass_context
def cli(ctx, server, remote, site, force_local):
    ctx.ensure_object(dict)
    ctx.obj["server"] = server
    if force_local:
        if remote or site:
            click.echo(
                "Warning: --local takes precedence over --remote/--site; "
                "ignoring those flags.",
                err=True,
            )
        ctx.obj["remote"] = None
        ctx.obj["remote_dir"] = DEFAULT_REMOTE_DIR
        ctx.obj["remote_port"] = None
        return
    resolved_spec, resolved_port = _resolve_remote(remote, site)
    if resolved_spec:
        host, remote_dir = _parse_remote(resolved_spec)
        ctx.obj["remote"] = host
        ctx.obj["remote_dir"] = remote_dir
        ctx.obj["remote_port"] = resolved_port
    else:
        ctx.obj["remote"] = None
        ctx.obj["remote_dir"] = DEFAULT_REMOTE_DIR
        ctx.obj["remote_port"] = None


@cli.command()
@click.argument("file_path")
@click.option("--title", default=None, help="Page title")
@click.option("--slug", default=None, help="URL slug")
@click.option("--theme", default=None, help="Theme name (geocities, academic, hacker, angelfire, web-ring)")
@click.option("--color-scheme", default=None, help="Color scheme (clean, neon, midnight, terminal, starfield, parchment)")
@click.option("--parent", default=None, help="Slug of the parent index page (for nested sections)")
@click.option("--tag", "tags", multiple=True, help="Tag this page (repeatable)")
@click.option("--excerpt", default=None, help="Short summary used by index list rendering")
@click.pass_context
def push(ctx, file_path, title, slug, theme, color_scheme, parent, tags, excerpt):
    """Push a file to the server as a published page."""
    path = Path(file_path)
    content = path.read_text()

    # For .md inputs, lift YAML frontmatter into structured fields. CLI flags
    # always win; only unset fields fall back to frontmatter values.
    merged = _merge_frontmatter(
        content, path.suffix.lower(),
        title=title, theme=theme, color_scheme=color_scheme,
        parent=parent, tags=tags, excerpt=excerpt, slug=slug,
    )
    content = merged["content"]
    title, theme, color_scheme = merged["title"], merged["theme"], merged["color_scheme"]
    parent, tags, excerpt = merged["parent"], merged["tags"], merged["excerpt"]
    slug = merged["slug"]
    index_spec = merged["index"]

    if not title:
        title = path.stem.replace("-", " ").replace("_", " ").title()

    remote = ctx.obj.get("remote")
    if remote:
        remote_path = _upload_bundle_to_remote(remote, path)
        args = f"push {shlex.quote(remote_path)} --title {shlex.quote(title)}"
        if slug:
            args += f" --slug {shlex.quote(slug)}"
        if theme:
            args += f" --theme {shlex.quote(theme)}"
        if color_scheme:
            args += f" --color-scheme {shlex.quote(color_scheme)}"
        if parent:
            args += f" --parent {shlex.quote(parent)}"
        for t in tags:
            args += f" --tag {shlex.quote(t)}"
        if excerpt:
            args += f" --excerpt {shlex.quote(excerpt)}"
        _remote_flubpub(remote, ctx.obj["remote_dir"], remote_port=ctx.obj["remote_port"], args=args)
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

    if suffix == ".html" and content.lstrip().startswith("<!--FLUBPUB"):
        click.echo("Detected index page (template will hydrate from #flubpub-pages)")

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
            if sys.stdin.isatty():
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
        if parent:
            body["parent"] = parent
        if tags:
            body["tags"] = list(tags)
        if excerpt:
            body["excerpt"] = excerpt
        if index_spec:
            body["index"] = index_spec

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
        _remote_flubpub(remote, ctx.obj["remote_dir"], remote_port=ctx.obj["remote_port"], args="list")
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
        _remote_flubpub(remote, ctx.obj["remote_dir"], remote_port=ctx.obj["remote_port"], args=f"get {shlex.quote(slug)}")
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
@click.option("--parent", default=None, help="Slug of the parent index page (for nested sections)")
@click.option("--tag", "tags", multiple=True, help="Tag this page (repeatable; replaces existing tags)")
@click.option("--excerpt", default=None, help="Short summary used by index list rendering")
@click.pass_context
def revise(ctx, slug, file_path, title, theme, color_scheme, parent, tags, excerpt):
    """Update an existing page with new content."""
    path = Path(file_path)

    remote = ctx.obj.get("remote")
    if remote:
        remote_path = _upload_bundle_to_remote(remote, path)
        args = f"revise {shlex.quote(slug)} {shlex.quote(remote_path)}"
        if title:
            args += f" --title {shlex.quote(title)}"
        if theme:
            args += f" --theme {shlex.quote(theme)}"
        if color_scheme:
            args += f" --color-scheme {shlex.quote(color_scheme)}"
        if parent:
            args += f" --parent {shlex.quote(parent)}"
        for t in tags:
            args += f" --tag {shlex.quote(t)}"
        if excerpt:
            args += f" --excerpt {shlex.quote(excerpt)}"
        _remote_flubpub(remote, ctx.obj["remote_dir"], remote_port=ctx.obj["remote_port"], args=args)
        _remote_cleanup(remote)
        return

    content = path.read_text()
    suffix = path.suffix.lower()

    # Mirror push: for .md, lift YAML frontmatter into structured fields.
    # CLI flags win; only unset fields fall back to frontmatter values.
    merged = _merge_frontmatter(
        content, suffix,
        title=title, theme=theme, color_scheme=color_scheme,
        parent=parent, tags=tags, excerpt=excerpt,
    )
    content = merged["content"]
    title, theme, color_scheme = merged["title"], merged["theme"], merged["color_scheme"]
    parent, tags, excerpt = merged["parent"], merged["tags"], merged["excerpt"]
    index_spec = merged["index"]

    if suffix == ".md":
        content_type = "markdown"
    elif suffix == ".html" and theme:
        content_type = "html"
    elif suffix == ".html":
        content_type = "html_raw"
    else:
        content_type = "html"

    # Mirror push's local-ref pipeline: scan for sibling assets/sub-pages,
    # upload them, and rewrite refs in the outgoing content. Without this,
    # revise would silently restore the source's pre-rewrite paths and break
    # asset URLs the previous push had fixed up.
    page_slug = slug
    server_base = ctx.obj["server"]
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
            if sys.stdin.isatty():
                click.confirm("These files will be uploaded. Continue?", abort=True)
        with httpx.Client() as upload_client:
            for asset in assets:
                with open(asset, "rb") as f:
                    resp = upload_client.post(
                        f"{server_base}/api/assets/{page_slug}",
                        files={"file": (asset.name, f)},
                    )
                if not resp.is_success:
                    click.echo(f"Error uploading {asset.name}: {resp.text}", err=True)
                    sys.exit(1)
                click.echo(f"Uploaded asset: {asset.name}")
        rewrite_mode = "html" if suffix == ".html" else "md"
        content = rewrite_refs(content, page_slug, assets, sub_pages, mode=rewrite_mode)

    body = {"content": content, "content_type": content_type}
    if title:
        body["title"] = title
    if theme:
        body["theme"] = theme
    if color_scheme:
        body["color_scheme"] = color_scheme
    if parent:
        body["parent"] = parent
    if tags:
        body["tags"] = list(tags)
    if excerpt:
        body["excerpt"] = excerpt
    if index_spec:
        body["index"] = index_spec

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
        _remote_flubpub(remote, ctx.obj["remote_dir"], remote_port=ctx.obj["remote_port"], args=f"delete {shlex.quote(slug)}")
        return

    with httpx.Client() as client:
        resp = client.delete(f"{ctx.obj['server']}/api/pages/{slug}")

    if resp.is_success:
        click.echo(f"Deleted: {slug}")
    else:
        click.echo(f"Error: {resp.text}", err=True)
        sys.exit(1)


INDEX_ASSETS_SLUG = "flubpub-index"


def _load_template_vars(vars_path: Path | None) -> dict:
    if not vars_path:
        return {}
    data = yaml.safe_load(vars_path.read_text()) or {}
    if not isinstance(data, dict):
        click.echo(
            f"Vars file must be a YAML mapping; got {type(data).__name__}",
            err=True,
        )
        sys.exit(1)
    return data


def _render_index_template(content: str, variables: dict) -> str:
    """Render an index HTML file through Jinja2. A template with no Jinja
    tags round-trips unchanged, so this is safe to call unconditionally."""
    return Template(content).render(**variables)


@cli.command(name="set-index")
@click.argument("file_path")
@click.option("--vars", "vars_file", default=None,
              type=click.Path(exists=True, dir_okay=False, path_type=Path),
              help="YAML file with Jinja variables (brand, tagline, etc).")
@click.pass_context
def set_index(ctx, file_path, vars_file):
    """Install a custom HTML file as the site index.

    The file is rendered as a Jinja2 template (defaults apply when no --vars
    is given), then scanned for local assets (imgs, css, js, fonts, url()
    refs), which are uploaded to /assets/flubpub-index/ with paths rewritten.
    A <script type="application/json" id="flubpub-pages"></script> marker in
    the file is filled with the current pages list at every rebuild.
    """
    path = Path(file_path)
    suffix = path.suffix.lower()
    if suffix not in (".html", ".md"):
        click.echo("Index must be a .html or .md file", err=True)
        sys.exit(1)

    is_markdown_index = suffix == ".md"
    variables = _load_template_vars(vars_file)
    # Markdown indexes don't run through Jinja — they're rendered server-side
    # into a minimal HTML shell or a flubpub theme. HTML indexes get the
    # existing Jinja pass. Frontmatter (title/theme/color_scheme/style_css/
    # index) on the markdown file becomes top-level IndexBody fields.
    md_body: dict = {}
    if is_markdown_index:
        rendered, fm = _split_md_frontmatter(path.read_text())
        if isinstance(fm, dict):
            for key in ("title", "theme", "color_scheme", "style_css", "index"):
                if key in fm and fm[key] is not None:
                    md_body[key] = fm[key]
    else:
        rendered = _render_index_template(path.read_text(), variables)

    remote = ctx.obj.get("remote")
    if remote:
        # For markdown indexes, upload the original .md with frontmatter
        # intact so the remote-side set-index re-parses theme/index/style_css
        # natively. Transcoding md -> rendered .html locally would strip the
        # frontmatter and the remote would see a raw HTML blob, losing the
        # theme and the index spec. HTML indexes still get the local Jinja
        # pass and are uploaded as rendered .html.
        if is_markdown_index:
            upload_path = path
            cleanup_path: Path | None = None
        else:
            with tempfile.NamedTemporaryFile(
                mode="w", dir=path.parent, prefix=".rendered-",
                suffix=".html", delete=False,
            ) as tf:
                tf.write(rendered)
                cleanup_path = Path(tf.name)
            upload_path = cleanup_path
        try:
            remote_path = _upload_bundle_to_remote(remote, upload_path)
            args = f"set-index {shlex.quote(remote_path)}"
            _remote_flubpub(remote, ctx.obj["remote_dir"], remote_port=ctx.obj["remote_port"], args=args)
            _remote_cleanup(remote)
        finally:
            if cleanup_path is not None:
                cleanup_path.unlink(missing_ok=True)
        return

    assets, sub_pages = scan_local_refs(path)
    if sub_pages:
        click.echo("Note: <a href> links to local .md/.html are ignored for the index.")

    if assets:
        click.echo("Local assets found:")
        for a in assets:
            click.echo(f"  ./{a.relative_to(path.parent.resolve())}")
        click.echo()
        if sys.stdin.isatty():
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
            rewrite_mode = "md" if is_markdown_index else "html"
            rendered = rewrite_refs(rendered, INDEX_ASSETS_SLUG, assets, [], mode=rewrite_mode)

        body = {"content": rendered}
        if is_markdown_index:
            body["content_type"] = "markdown"
            body.update(md_body)
        resp = client.post(f"{server}/api/index", json=body)

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
        _remote_flubpub(remote, ctx.obj["remote_dir"], remote_port=ctx.obj["remote_port"], args="unset-index")
        return

    with httpx.Client() as client:
        resp = client.delete(f"{ctx.obj['server']}/api/index")

    if resp.is_success:
        click.echo("Custom index removed.")
    else:
        click.echo(f"Error: {resp.text}", err=True)
        sys.exit(1)


def _find_templates_dir() -> Path | None:
    """Locate the templates/ directory. Prefer CWD; fall back to the bundled
    location alongside the installed package."""
    cwd_dir = Path("templates")
    if cwd_dir.is_dir():
        return cwd_dir.resolve()

    import flubpub
    pkg_root = Path(flubpub.__file__).resolve().parent.parent.parent
    bundled = pkg_root / "templates"
    if bundled.is_dir():
        return bundled
    return None


def _read_template_meta(template_dir: Path) -> dict:
    meta_path = template_dir / "template.yml"
    if not meta_path.is_file():
        return {}
    try:
        data = yaml.safe_load(meta_path.read_text()) or {}
    except yaml.YAMLError:
        return {}
    return data if isinstance(data, dict) else {}


def _template_default_vars(meta: dict) -> dict:
    """Extract a {name: default} mapping from a template.yml's `vars` list."""
    defaults: dict = {}
    for entry in meta.get("vars") or []:
        if isinstance(entry, dict) and "name" in entry:
            defaults[entry["name"]] = entry.get("default")
    return defaults


@cli.command(name="list-index-templates")
def list_index_templates():
    """List available index templates discovered under templates/."""
    templates_dir = _find_templates_dir()
    if templates_dir is None:
        click.echo("No templates/ directory found in CWD or alongside the package.")
        return

    rows: list[tuple[str, str]] = []
    for sub in sorted(p for p in templates_dir.iterdir() if p.is_dir()):
        if not (sub / "index.html").is_file():
            continue
        meta = _read_template_meta(sub)
        name = meta.get("name") or sub.name
        desc = (meta.get("description") or "").strip().replace("\n", " ")
        if len(desc) > 60:
            desc = desc[:57] + "..."
        rows.append((name, desc))

    if not rows:
        click.echo(f"No templates found under {templates_dir}.")
        return

    name_w = max(len("NAME"), max(len(r[0]) for r in rows))
    click.echo(f"{'NAME':<{name_w}}  {'DESCRIPTION'}")
    click.echo("-" * (name_w + 2 + 60))
    for name, desc in rows:
        click.echo(f"{name:<{name_w}}  {desc}")


@cli.command(name="new-index")
@click.option("--template", "template_name", required=True,
              help="Template name (folder under templates/)")
@click.option("--slug", default=None,
              help="Slug hint (used as a Jinja var if the template references it)")
@click.option("--vars", "vars_file", default=None,
              type=click.Path(exists=True, dir_okay=False, path_type=Path),
              help="YAML file with Jinja variables to merge over template defaults")
@click.option("--output", "output_path", default=None,
              type=click.Path(dir_okay=False, path_type=Path),
              help="Write rendered HTML here (default: stdout)")
@click.option("--copy-assets", is_flag=True, default=False,
              help="Copy template's other files (CSS/JS/etc) next to --output")
def new_index(template_name, slug, vars_file, output_path, copy_assets):
    """Generate a working index file from a template (local-only operation)."""
    templates_dir = _find_templates_dir()
    if templates_dir is None:
        click.echo("No templates/ directory found in CWD or alongside the package.", err=True)
        sys.exit(1)

    template_dir = templates_dir / template_name
    template_html = template_dir / "index.html"
    if not template_html.is_file():
        click.echo(f"Template '{template_name}' not found at {template_html}", err=True)
        sys.exit(1)

    meta = _read_template_meta(template_dir)
    variables = _template_default_vars(meta)
    variables.update(_load_template_vars(vars_file))
    if slug and "slug" not in variables:
        variables["slug"] = slug

    rendered = _render_index_template(template_html.read_text(), variables)

    if copy_assets and not output_path:
        click.echo("--copy-assets requires --output.", err=True)
        sys.exit(1)

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered)
        click.echo(f"Wrote {output_path}")
        if copy_assets:
            dest_dir = output_path.parent
            for item in template_dir.iterdir():
                if item.name in ("index.html", "template.yml"):
                    continue
                target = dest_dir / item.name
                if item.is_dir():
                    shutil.copytree(item, target, dirs_exist_ok=True)
                else:
                    shutil.copy2(item, target)
                click.echo(f"Copied asset: {item.name}")
    else:
        click.echo(rendered)


@cli.command(name="index-payload")
@click.argument("slug")
@click.pass_context
def index_payload_cmd(ctx, slug):
    """Print the filtered/sorted JSON payload an index page would render."""
    remote = ctx.obj.get("remote")
    if remote:
        _remote_flubpub(remote, ctx.obj["remote_dir"], remote_port=ctx.obj["remote_port"], args=f"index-payload {shlex.quote(slug)}")
        return

    from flubpub.index_payload import build_index_payload
    from flubpub.models import IndexSpec

    server = ctx.obj["server"]
    with httpx.Client() as client:
        resp = client.get(f"{server}/api/pages/{slug}")
        if not resp.is_success:
            click.echo(f"Error: {resp.text}", err=True)
            sys.exit(1)
        entry = resp.json()

        if entry.get("content_type") != "index":
            click.echo(f"Page '{slug}' is not an index page (content_type={entry.get('content_type')!r}).", err=True)
            sys.exit(1)

        index_block = entry.get("index") or {}
        try:
            spec = IndexSpec(**index_block)
        except Exception as e:
            click.echo(f"Could not build IndexSpec from entry: {e}", err=True)
            sys.exit(1)

        all_resp = client.get(f"{server}/api/pages")
        if not all_resp.is_success:
            click.echo(f"Error fetching page list: {all_resp.text}", err=True)
            sys.exit(1)
        all_pages = all_resp.json()

    payload = build_index_payload(spec, all_pages, self_slug=slug)
    click.echo(json.dumps(payload, indent=2, default=str))


@cli.command()
@click.option("--host", default="0.0.0.0", show_default=True, help="Bind host")
@click.option("--port", default=8000, show_default=True, help="Bind port")
def serve(host, port):
    """Start the flubpub server."""
    import uvicorn
    uvicorn.run("flubpub.server:app", host=host, port=port)


@cli.command()
@click.option("--site", "site_key", default=None,
              help="Site key from the registry. Defaults to [default].")
@click.option("--script", default="deploy/deploy.sh", show_default=True,
              help="Path to the deploy script.")
def deploy(site_key, script):
    """Deploy a site from the registry. Reads remote/server_name/port from
    ~/.config/flubpub/sites.toml and shells out to deploy.sh with the
    derived env vars."""
    cfg = _load_sites_config()
    site_key = site_key or os.environ.get("FLUBPUB_SITE") or cfg.get("default")
    if not site_key:
        click.echo("No --site given and no [default] in config.", err=True)
        sys.exit(1)
    entry = (cfg.get("sites") or {}).get(site_key)
    if not entry:
        click.echo(f"Site '{site_key}' not found in {SITES_CONFIG_PATH}.", err=True)
        sys.exit(1)
    missing = [k for k in ("remote", "server_name", "port") if not entry.get(k)]
    if missing:
        click.echo(
            f"Site '{site_key}' is missing required keys for deploy: {missing}. "
            f"Run `flubpub sites add {site_key} <remote> "
            f"--server-name <host> --port <n>` to fill them in.",
            err=True,
        )
        sys.exit(1)
    host, install_dir = _parse_remote(entry["remote"])
    user, _, hostname = host.partition("@")
    if not hostname:
        user, hostname = "root", host

    script_path = Path(script)
    if not script_path.is_file():
        click.echo(f"Deploy script not found at {script_path}", err=True)
        sys.exit(1)

    email = (
        entry.get("email")
        or cfg.get("acme_email")
        or os.environ.get("EMAIL")
        or ""
    )

    env = {
        **os.environ,
        "SITE": site_key,
        "REMOTE_USER": user,
        "REMOTE_HOST": hostname,
        "REMOTE_DIR": install_dir,
        "SERVER_NAME": entry["server_name"],
        "PORT": str(entry["port"]),
        "EMAIL": email,
        "DISPLAY_TZ": str(
            entry.get("display_tz")
            or cfg.get("display_tz")
            or os.environ.get("DISPLAY_TZ")
            or ""
        ),
    }
    click.echo(f"Deploying '{site_key}' via {script_path}")
    click.echo(f"  → {user}@{hostname}:{install_dir}")
    click.echo(f"  → {entry['server_name']}:{entry['port']}")
    click.echo(f"  → tls: {'certbot (' + email + ')' if email else 'http only'}")
    rc = subprocess.run(["bash", str(script_path)], env=env).returncode
    sys.exit(rc)


@cli.group()
def sites():
    """Manage the sites registry at ~/.config/flubpub/sites.toml."""


def _save_sites_config(cfg: dict) -> None:
    SITES_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    if "default" in cfg:
        lines.append(f'default = "{cfg["default"]}"\n')
    if "acme_email" in cfg:
        lines.append(f'acme_email = "{cfg["acme_email"]}"\n')
    for key, entry in (cfg.get("sites") or {}).items():
        lines.append(f'\n[sites.{key}]\n')
        for k, v in entry.items():
            if isinstance(v, int):
                lines.append(f'{k} = {v}\n')
            else:
                lines.append(f'{k} = "{v}"\n')
    SITES_CONFIG_PATH.write_text("".join(lines))


@sites.command(name="list")
def sites_list():
    """List configured sites."""
    cfg = _load_sites_config()
    site_map = cfg.get("sites") or {}
    if not site_map:
        click.echo(f"No sites configured. Edit {SITES_CONFIG_PATH} or run `flubpub sites add`.")
        return
    default = cfg.get("default")
    width = max(len("KEY"), max(len(k) for k in site_map))
    click.echo(f"{'KEY':<{width}}  REMOTE")
    click.echo("-" * (width + 2 + 50))
    for key, entry in site_map.items():
        marker = "*" if key == default else " "
        click.echo(f"{marker} {key:<{width-2}}  {entry.get('remote', '(missing)')}")
    if default:
        click.echo(f"\n(* = default)")


@sites.command(name="add")
@click.argument("key")
@click.argument("remote_spec")
@click.option("--server-name", default=None,
              help="Public hostname nginx should match (e.g. example.com). "
                   "Required for `flubpub deploy`.")
@click.option("--port", type=int, default=None,
              help="TCP port for this site's uvicorn (e.g. 8001). "
                   "Required for `flubpub deploy`.")
@click.option("--email", default=None,
              help="ACME contact email. If set, `flubpub deploy` requests "
                   "a Let's Encrypt cert via certbot. Falls back to top-level "
                   "`acme_email` or the EMAIL env var.")
@click.option("--default", "make_default", is_flag=True, default=False,
              help="Also set this site as the default.")
def sites_add(key, remote_spec, server_name, port, email, make_default):
    """Add or update a site entry. REMOTE_SPEC is e.g. root@host:/opt/flubpub-key."""
    cfg = _load_sites_config()
    entry = cfg.setdefault("sites", {}).setdefault(key, {})
    entry["remote"] = remote_spec
    if server_name is not None:
        entry["server_name"] = server_name
    if port is not None:
        entry["port"] = port
    if email is not None:
        entry["email"] = email
    if make_default or "default" not in cfg:
        cfg["default"] = key
    _save_sites_config(cfg)
    click.echo(f"Site '{key}' → {remote_spec}")
    if server_name:
        click.echo(f"  server_name: {server_name}")
    if port:
        click.echo(f"  port:        {port}")
    if email:
        click.echo(f"  email:       {email}")
    if cfg.get("default") == key:
        click.echo(f"(default)")


@sites.command(name="set-default")
@click.argument("key")
def sites_set_default(key):
    """Set the default site key."""
    cfg = _load_sites_config()
    if key not in (cfg.get("sites") or {}):
        click.echo(f"Site '{key}' not configured.", err=True)
        sys.exit(1)
    cfg["default"] = key
    _save_sites_config(cfg)
    click.echo(f"Default → {key}")


@sites.command(name="remove")
@click.argument("key")
def sites_remove(key):
    """Remove a site entry."""
    cfg = _load_sites_config()
    if key not in (cfg.get("sites") or {}):
        click.echo(f"Site '{key}' not configured.", err=True)
        sys.exit(1)
    del cfg["sites"][key]
    if cfg.get("default") == key:
        cfg.pop("default", None)
    _save_sites_config(cfg)
    click.echo(f"Removed '{key}'.")
