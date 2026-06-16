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
from datetime import datetime, timezone
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


def _explicit_overrides(*, title=None, slug=None, theme=None, color_scheme=None,
                        parent=None, tags=(), excerpt=None, description=None) -> dict:
    """Collect only the flags the user actually passed, mapped to their
    frontmatter key. None / empty-tuple means "not given" and is skipped, so
    we never clobber frontmatter with a default."""
    out: dict = {}
    if title is not None:
        out["title"] = title
    if slug is not None:
        out["slug"] = slug
    if theme is not None:
        out["theme"] = theme
    if color_scheme is not None:
        out["color_scheme"] = color_scheme
    if parent is not None:
        out["parent"] = parent
    if excerpt is not None:
        out["excerpt"] = excerpt
    if description is not None:
        out["description"] = description
    if tags:
        out["tags"] = list(tags)
    return out


def _apply_cli_overrides_to_md_file(path: Path, overrides: dict) -> None:
    """In-file SoT: when a CLI flag is given for a `.md` push/revise, the
    frontmatter is the source of truth, so persist the override *into the
    file's frontmatter first*, then let the normal push read the now-canonical
    file. Best of both worlds — CLI ergonomics, frontmatter durability.

    `overrides` maps frontmatter key → value, containing only flags the user
    explicitly passed (None / empty are pre-filtered by the caller). A clear
    per-key diagnostic is printed for every change. If the file can't be
    written (e.g. a read-only /tmp scratch), a warning is emitted and the push
    proceeds with the merged values un-persisted."""
    if path.suffix.lower() != ".md" or not overrides:
        return
    body, fm = _split_md_frontmatter(path.read_text())
    fm = dict(fm) if isinstance(fm, dict) else {}
    changes: list[str] = []
    for key, new in overrides.items():
        old = fm.get(key)
        if old == new:
            continue
        fm[key] = new
        shown_old = "(unset)" if old is None else repr(old)
        changes.append(f"{key}: {shown_old} → {new!r}")
    if not changes:
        return
    fm_text = yaml.safe_dump(fm, sort_keys=False, default_flow_style=False,
                             allow_unicode=True).strip()
    new_text = f"---\n{fm_text}\n---\n{body}"
    try:
        path.write_text(new_text)
    except OSError as e:
        click.echo(
            f"Warning: {path.name}: could not persist frontmatter ({e}); "
            f"pushing merged values without updating the source file.",
            err=True,
        )
        return
    click.echo(f"{path.name}: frontmatter updated (in-file SoT)")
    for c in changes:
        click.echo(f"  {c}")


def _merge_frontmatter(content: str, suffix: str, *,
                       title: str | None, theme: str | None,
                       color_scheme: str | None, parent: str | None,
                       tags: tuple, excerpt: str | None,
                       description: str | None = None,
                       slug: str | None = None) -> dict:
    """For .md inputs, parse YAML frontmatter and merge into the supplied
    CLI-flag values — CLI flags always win. Returns a dict with the
    (possibly-stripped) content and the resolved fields. The `index` key,
    if present in the frontmatter, is lifted into a structured field the
    server promotes to a markdown-sourced index page."""
    out = {
        "content": content, "title": title, "theme": theme,
        "color_scheme": color_scheme, "parent": parent,
        "tags": tags, "excerpt": excerpt, "description": description,
        "slug": slug, "index": None,
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
    out["description"]  = description  or fm.get("description")
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


SITES_CONFIG_DIR = Path.home() / ".config" / "flubpub"
SITES_CONFIG_PATH = SITES_CONFIG_DIR / "sites.json"
_LEGACY_SITES_TOML = SITES_CONFIG_DIR / "sites.toml"


def _load_sites_config() -> dict:
    """Read the sites registry (JSON). Returns {} if absent or unreadable.

    The registry is plain JSON — read and written symmetrically with the same
    library, no hand-rolled emitter. A pre-JSON `sites.toml` is not read
    silently; run `python3 migrate-sites-config.py` (a delete-after-use
    one-off at the repo root) to convert it once."""
    if not SITES_CONFIG_PATH.is_file():
        if _LEGACY_SITES_TOML.is_file():
            click.echo(
                f"Found legacy {_LEGACY_SITES_TOML} but no {SITES_CONFIG_PATH.name}. "
                f"Run `python3 migrate-sites-config.py` to convert it.",
                err=True,
            )
        return {}
    try:
        data = json.loads(SITES_CONFIG_PATH.read_text())
    except json.JSONDecodeError as e:
        click.echo(f"Warning: could not parse {SITES_CONFIG_PATH}: {e}", err=True)
        return {}
    return data if isinstance(data, dict) else {}


def _resolve_remote(
    remote: str | None, site: str | None
) -> tuple[str | None, int | None, str | None]:
    """Resolve --remote / --site / default-from-config / FLUBPUB_SITE env into
    a (remote_spec, port, site_key) triple. Returns (None, None, None) for
    local-HTTP mode. The port is taken from the registry when --site is used
    (or default). site_key is the registry key publishes mirror into under
    content/; it is None when it can't be determined (a raw --remote spec with
    no matching registry entry, or local-HTTP mode), which disables mirroring."""
    cfg = _load_sites_config()
    sites = cfg.get("sites") or {}
    if remote:
        # Reverse-map a raw --remote spec back onto a registry key so the
        # content/ mirror still partitions correctly. No match → no mirror
        # (the raw escape hatch isn't registry-backed).
        key = next(
            (k for k, e in sites.items()
             if isinstance(e, dict) and e.get("remote") == remote),
            None,
        )
        return remote, None, key
    site = site or os.environ.get("FLUBPUB_SITE")
    if not site:
        site = cfg.get("default")
    if not site:
        return None, None, None
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
    return spec, port, site


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


def _content_root() -> Path | None:
    """Locate the SSOT content/ directory.

    Resolution order:
      1. the registry's top-level `content_root` (absolute path to the repo
         that owns content/) — this makes "publish from anywhere" literally
         true: you can push a draft from /tmp and the canonical tree still
         updates, because the root is configured, not inferred from CWD;
      2. fallback — walk up from CWD to the nearest .git/pyproject.toml marker
         (works with zero config when you happen to be inside the repo).
    Returns None when neither resolves (mirroring is skipped, with a notice)."""
    configured = (_load_sites_config() or {}).get("content_root")
    if configured:
        repo = Path(configured).expanduser()
        if repo.is_dir():
            return repo / "content"
        click.echo(
            f"Note: configured content_root {configured!r} is not a directory; "
            f"falling back to CWD-walk for the content/ mirror.",
            err=True,
        )
    cur = Path.cwd().resolve()
    for d in (cur, *cur.parents):
        if (d / ".git").exists() or (d / "pyproject.toml").is_file():
            return d / "content"
    return None


def _mirror_bundle_pairs(
    slug: str, entry: Path, dest_dir: Path
) -> tuple[list[tuple[Path, Path]], bool]:
    """Plan the (src, dest) copies that mirror `entry` plus its ref-closure
    into content/<site>/. A ref-free single file lands flat as
    content/<site>/<slug>.<ext>; anything with assets/sub-pages lands in a
    content/<site>/<slug>/ directory preserving each file's path relative to
    the entry's own directory (the entry keeps its source filename). Returns
    (pairs, is_dir_shape)."""
    suffix = entry.suffix.lower()
    assets, subs = collect_all_refs(entry) if suffix in PAGE_SUFFIXES else ([], [])
    if not assets and not subs:
        return [(entry, dest_dir / f"{slug}{entry.suffix}")], False
    bundle_root = dest_dir / slug
    base = entry.parent.resolve()
    pairs = [(entry, bundle_root / entry.name)]
    for ref in assets + subs:
        try:
            rel = ref.resolve().relative_to(base).as_posix()
        except ValueError:
            rel = ref.name
        pairs.append((ref, bundle_root / rel))
    return pairs, True


def _mirror_to_content(site_key: str, slug: str, entry_path: Path) -> None:
    """Copy a just-published bundle into content/<site_key>/ so the tree
    stays canonical without manual upkeep, keeping exactly one shape per
    slug (drops the opposite flat/dir form)."""
    root = _content_root()
    if root is None:
        click.echo(
            "Note: flubpub repo root not found (no .git/pyproject.toml above "
            "CWD); skipping content/ mirror.",
            err=True,
        )
        return
    entry = entry_path.resolve()
    dest_dir = root / site_key
    pairs, is_dir = _mirror_bundle_pairs(slug, entry, dest_dir)

    wrote = False
    for src, dest in pairs:
        # Don't copy a file onto itself — shutil.copy2 raises SameFileError,
        # and there is nothing to do when the published file already is the
        # canonical copy.
        if src.resolve() == dest.resolve():
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        wrote = True

    # Drop the opposite flat/dir form *after* writing, so a source that
    # lived inside the old shape has already been copied out before the
    # old shape is removed.
    if is_dir:
        for ext in (".md", ".html"):
            (dest_dir / f"{slug}{ext}").unlink(missing_ok=True)
    else:
        shutil.rmtree(dest_dir / slug, ignore_errors=True)

    if wrote:
        click.echo(f"Mirrored → content/{site_key}/")


def _unmirror_from_content(site_key: str, slug: str) -> None:
    """Drop a deleted page's canonical copy from content/<site_key>/ so a
    delete doesn't leave the tree claiming a page that no longer exists."""
    root = _content_root()
    if root is None:
        click.echo(
            "Note: flubpub repo root not found (no .git/pyproject.toml above "
            "CWD); skipping content/ unmirror.",
            err=True,
        )
        return
    dest_dir = root / site_key
    removed: list[str] = []
    for ext in (".md", ".html"):
        f = dest_dir / f"{slug}{ext}"
        if f.is_file():
            f.unlink()
            removed.append(f.name)
    d = dest_dir / slug
    if d.is_dir():
        shutil.rmtree(d)
        removed.append(f"{slug}/")
    if removed:
        click.echo(f"Removed from content/{site_key}/: {', '.join(removed)}")


# --- html-article metadata SSOT: content/<site>/_pages.yaml ------------------
# An html article has no frontmatter, so the pages.json fields with no other
# SSOT home (description, tags, theme, ...) are mirrored here, keyed by slug.
# md articles keep their frontmatter and are never written here.
PAGES_META_NAME = "_pages.yaml"
_PAGES_META_FIELDS = ("title", "description", "tags", "theme",
                      "color_scheme", "parent", "excerpt")


def _pages_meta_path(site_key: str) -> Path | None:
    root = _content_root()
    return None if root is None else root / site_key / PAGES_META_NAME


def _load_pages_meta(path: Path) -> dict:
    if not path.is_file():
        return {}
    data = yaml.safe_load(path.read_text()) or {}
    return data if isinstance(data, dict) else {}


def _save_pages_meta(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=True,
                                   default_flow_style=False))


def _write_pages_meta(site_key: str, slug: str, entry_path: Path,
                      meta: dict) -> None:
    """Upsert an html article's pages.json-only metadata into _pages.yaml. A
    no-op for .md (frontmatter is its SSOT). Merges rather than replaces: only
    non-empty provided fields are set, so a content-only revise that omits
    --description keeps the stored value, matching the server's partial PUT."""
    if entry_path.suffix.lower() != ".html":
        return
    path = _pages_meta_path(site_key)
    if path is None:
        return
    data = _load_pages_meta(path)
    entry = dict(data.get(slug) or {})
    for key in _PAGES_META_FIELDS:
        val = list(meta.get(key)) if key == "tags" and meta.get(key) else meta.get(key)
        if val:
            entry[key] = val
    data[slug] = entry
    _save_pages_meta(path, data)
    click.echo(f"Recorded metadata → content/{site_key}/{PAGES_META_NAME}")


def _remove_pages_meta(site_key: str, slug: str) -> None:
    """Drop a slug from _pages.yaml (no-op if absent, e.g. an md page)."""
    path = _pages_meta_path(site_key)
    if path is None:
        return
    data = _load_pages_meta(path)
    if slug in data:
        del data[slug]
        _save_pages_meta(path, data)
        click.echo(f"Removed {slug} from content/{site_key}/{PAGES_META_NAME}")


def _read_pages_meta(site_key: str, slug: str) -> dict:
    """Return an html article's stored metadata subset, or {} (md / absent)."""
    path = _pages_meta_path(site_key)
    if path is None:
        return {}
    return dict(_load_pages_meta(path).get(slug) or {})


def _should_mirror(ctx) -> bool:
    return bool(ctx.obj.get("mirror")) and bool(ctx.obj.get("site_key"))


# `sync` reads a small per-site manifest at content/<site>/_manifest.toml to
# learn which file is the index. The manifest is intentionally minimal — let
# it grow organically rather than designing an ontology up front.
SITE_MANIFEST_NAME = "_manifest.toml"
RECYCLE_DIR_NAME = ".recycle"


def _load_site_manifest(site_dir: Path) -> dict:
    path = site_dir / SITE_MANIFEST_NAME
    if not path.is_file():
        return {}
    import tomllib
    try:
        return tomllib.loads(path.read_text())
    except tomllib.TOMLDecodeError as e:
        click.echo(f"Warning: could not parse {path}: {e}", err=True)
        return {}


def _find_bundle_entry(bundle_dir: Path) -> Path | None:
    """Pick the entry file inside a content bundle dir. Prefers
    `<slug>.{html,md}`, falls back to `index.{html,md}`."""
    slug = bundle_dir.name
    for name in (f"{slug}.html", f"{slug}.md", "index.html", "index.md"):
        p = bundle_dir / name
        if p.is_file():
            return p
    return None


def _enumerate_content_site(site_dir: Path) -> tuple[Path | None, dict[str, Path]]:
    """Walk content/<site>/ and classify entries. Returns (index_entry, {slug:
    entry_path}). The index is named explicitly in `_manifest.toml`; hidden
    names, the manifest itself, and `.recycle/` are skipped."""
    if not site_dir.is_dir():
        return None, {}
    manifest = _load_site_manifest(site_dir)
    index_entry: Path | None = None
    index_decl = manifest.get("index")
    if isinstance(index_decl, str) and index_decl:
        cand = (site_dir / index_decl).resolve()
        if cand.is_file() and site_dir.resolve() in cand.parents:
            index_entry = cand
        else:
            click.echo(
                f"Warning: manifest index '{index_decl}' not found under "
                f"content/{site_dir.name}/.",
                err=True,
            )

    pages: dict[str, Path] = {}
    for item in sorted(site_dir.iterdir()):
        if item.name.startswith(".") or item.name == RECYCLE_DIR_NAME:
            continue
        if item.name == SITE_MANIFEST_NAME:
            continue
        if index_entry is not None and item.resolve() == index_entry:
            continue
        if item.is_file() and item.suffix.lower() in PAGE_SUFFIXES:
            pages[item.stem] = item
            continue
        if item.is_dir():
            entry = _find_bundle_entry(item)
            if entry is None:
                click.echo(
                    f"  skip content/{site_dir.name}/{item.name}/: no entry file "
                    f"(looked for {item.name}.{{html,md}}, index.{{html,md}})",
                    err=True,
                )
                continue
            pages[item.name] = entry
    return index_entry, pages


def _remote_pages_index(remote: str, remote_dir: str) -> list[dict]:
    """Read the remote's data/pages.json via ssh. Returns [] when missing."""
    result = subprocess.run(
        ["ssh", remote, f"cat {shlex.quote(remote_dir)}/data/pages.json 2>/dev/null || echo '[]'"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        click.echo(f"SSH error reading pages.json: {result.stderr.strip()}", err=True)
        sys.exit(1)
    try:
        data = json.loads(result.stdout or "[]")
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def _recycle_remote_page(remote: str, remote_dir: str, bin_dir: Path,
                         slug: str, meta: dict) -> None:
    """Capture a remote page (entry file + assets + metadata) into the local
    recycle bin before deletion. Best-effort: a missing assets dir is not
    fatal, since not every page has one."""
    bin_dir.mkdir(parents=True, exist_ok=True)
    # Entry file. The remote keeps these as `pages/<slug>.{md,html}` — try both
    # rather than glob-via-ssh to keep behavior predictable.
    for ext in (".html", ".md"):
        src = f"{remote}:{remote_dir}/site/src/pages/{slug}{ext}"
        r = subprocess.run(
            ["scp", "-q", src, str(bin_dir / f"{slug}{ext}")],
            capture_output=True, text=True,
        )
        if r.returncode == 0:
            break
    assets_src = f"{remote}:{remote_dir}/site/src/assets/{slug}"
    subprocess.run(
        ["scp", "-rq", assets_src, str(bin_dir / "assets")],
        capture_output=True, text=True,
    )
    (bin_dir / "metadata.json").write_text(json.dumps(meta, indent=2))


@click.group()
@click.option("--server", default="http://localhost:8000", show_default=True, help="Server base URL")
@click.option("--remote", default=None,
              help="SSH remote (e.g. root@host[:/abs/path]). Overrides --site.")
@click.option("--site", default=None,
              help="Site key from ~/.config/flubpub/sites.json. "
                   "Falls back to FLUBPUB_SITE env or [default].")
@click.option("--local", "force_local", is_flag=True, default=False,
              help="Bypass the sites registry entirely and target --server "
                   "(default http://localhost:8000). USE WHEN TESTING LOCALLY "
                   "to avoid silently pushing through SSH to a production "
                   "site listed as `default` in ~/.config/flubpub/sites.json.")
@click.option("--no-mirror", "no_mirror", is_flag=True, default=False,
              help="Skip mirroring the published bundle into content/. By "
                   "default every push/revise/set-index/delete keeps "
                   "content/<site>/ canonical automatically. Also disabled by "
                   "FLUBPUB_NO_MIRROR=1.")
@click.pass_context
def cli(ctx, server, remote, site, force_local, no_mirror):
    ctx.ensure_object(dict)
    ctx.obj["server"] = server
    mirror_disabled = no_mirror or os.environ.get("FLUBPUB_NO_MIRROR") in ("1", "true", "yes")
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
        ctx.obj["site_key"] = None
        ctx.obj["mirror"] = False
        return
    ctx.obj["mirror"] = not mirror_disabled
    resolved_spec, resolved_port, resolved_key = _resolve_remote(remote, site)
    if resolved_spec:
        host, remote_dir = _parse_remote(resolved_spec)
        ctx.obj["remote"] = host
        ctx.obj["remote_dir"] = remote_dir
        ctx.obj["remote_port"] = resolved_port
        ctx.obj["site_key"] = resolved_key
    else:
        ctx.obj["remote"] = None
        ctx.obj["remote_dir"] = DEFAULT_REMOTE_DIR
        ctx.obj["remote_port"] = None
        ctx.obj["site_key"] = None


@cli.command()
@click.argument("file_path")
@click.option("--title", default=None, help="Page title")
@click.option("--slug", default=None, help="URL slug")
@click.option("--theme", default=None, help="Theme name (geocities, academic, hacker, angelfire, web-ring)")
@click.option("--color-scheme", default=None, help="Color scheme (clean, neon, midnight, terminal, starfield, parchment)")
@click.option("--parent", default=None, help="Slug of the parent index page (for nested sections)")
@click.option("--tag", "tags", multiple=True, help="Tag this page (repeatable)")
@click.option("--excerpt", default=None, help="Short summary used by index list rendering")
@click.option("--description", default=None, help="Longer per-page subtitle displayed under links in custom index lists")
@click.pass_context
def push(ctx, file_path, title, slug, theme, color_scheme, parent, tags, excerpt, description):
    """Push a file to the server as a published page."""
    path = Path(file_path)

    # In-file SoT: persist any explicit CLI override into the .md frontmatter
    # first, so the source file (and its content/ mirror) stays canonical.
    _apply_cli_overrides_to_md_file(path, _explicit_overrides(
        title=title, slug=slug, theme=theme, color_scheme=color_scheme,
        parent=parent, tags=tags, excerpt=excerpt, description=description,
    ))
    content = path.read_text()

    # For .md inputs, lift YAML frontmatter into structured fields. CLI flags
    # always win; only unset fields fall back to frontmatter values.
    merged = _merge_frontmatter(
        content, path.suffix.lower(),
        title=title, theme=theme, color_scheme=color_scheme,
        parent=parent, tags=tags, excerpt=excerpt, description=description,
        slug=slug,
    )
    content = merged["content"]
    title, theme, color_scheme = merged["title"], merged["theme"], merged["color_scheme"]
    parent, tags, excerpt = merged["parent"], merged["tags"], merged["excerpt"]
    description = merged["description"]
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
        if description:
            args += f" --description {shlex.quote(description)}"
        _remote_flubpub(remote, ctx.obj["remote_dir"], remote_port=ctx.obj["remote_port"], args=args)
        _remote_cleanup(remote)
        if _should_mirror(ctx):
            mirror_slug = slug or _slugify(title)
            _mirror_to_content(ctx.obj["site_key"], mirror_slug, path)
            _write_pages_meta(ctx.obj["site_key"], mirror_slug, path, {
                "title": title, "description": description, "tags": tags,
                "theme": theme, "color_scheme": color_scheme,
                "parent": parent, "excerpt": excerpt,
            })
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
        if description:
            body["description"] = description
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
@click.option("--description", default=None, help="Longer per-page subtitle displayed under links in custom index lists")
@click.pass_context
def revise(ctx, slug, file_path, title, theme, color_scheme, parent, tags, excerpt, description):
    """Update an existing page with new content."""
    path = Path(file_path)

    # In-file SoT: persist explicit CLI overrides into the .md frontmatter
    # before anything reads/uploads/mirrors the file (revise has no --slug).
    _apply_cli_overrides_to_md_file(path, _explicit_overrides(
        title=title, theme=theme, color_scheme=color_scheme,
        parent=parent, tags=tags, excerpt=excerpt, description=description,
    ))

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
        if description:
            args += f" --description {shlex.quote(description)}"
        _remote_flubpub(remote, ctx.obj["remote_dir"], remote_port=ctx.obj["remote_port"], args=args)
        _remote_cleanup(remote)
        if _should_mirror(ctx):
            _mirror_to_content(ctx.obj["site_key"], slug, path)
            _write_pages_meta(ctx.obj["site_key"], slug, path, {
                "title": title, "description": description, "tags": tags,
                "theme": theme, "color_scheme": color_scheme,
                "parent": parent, "excerpt": excerpt,
            })
        return

    content = path.read_text()
    suffix = path.suffix.lower()

    # Mirror push: for .md, lift YAML frontmatter into structured fields.
    # CLI flags win; only unset fields fall back to frontmatter values.
    merged = _merge_frontmatter(
        content, suffix,
        title=title, theme=theme, color_scheme=color_scheme,
        parent=parent, tags=tags, excerpt=excerpt, description=description,
    )
    content = merged["content"]
    title, theme, color_scheme = merged["title"], merged["theme"], merged["color_scheme"]
    parent, tags, excerpt = merged["parent"], merged["tags"], merged["excerpt"]
    description = merged["description"]
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
    if description:
        body["description"] = description
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
        if _should_mirror(ctx):
            _unmirror_from_content(ctx.obj["site_key"], slug)
            _remove_pages_meta(ctx.obj["site_key"], slug)
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
    # through the unified page-type model (one index model — see server.py
    # set_custom_index). HTML indexes get the existing Jinja pass. Frontmatter
    # (title/theme/color_scheme/index) on the markdown file becomes top-level
    # IndexBody fields.
    md_body: dict = {}
    if is_markdown_index:
        rendered, fm = _split_md_frontmatter(path.read_text())
        if isinstance(fm, dict):
            for key in ("title", "theme", "color_scheme", "index"):
                if key in fm and fm[key] is not None:
                    md_body[key] = fm[key]
    else:
        rendered = _render_index_template(path.read_text(), variables)

    remote = ctx.obj.get("remote")
    if remote:
        # For markdown indexes, upload the original .md with frontmatter
        # intact so the remote-side set-index re-parses theme/index
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
            if _should_mirror(ctx):
                _mirror_to_content(ctx.obj["site_key"], path.stem, path)
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


@cli.command()
@click.option("--dry-run", is_flag=True, default=False,
              help="Show the plan without making any remote changes.")
@click.pass_context
def sync(ctx, dry_run):
    """Reconcile remote site with content/<site>/ as the source of truth.

    Pushes new entries, revises existing ones, and recycles remote-only pages
    into content/<site>/.recycle/<UTC-ts>/<slug>/ before deleting them. Looks
    for `home.{md,html}` at the content root and re-applies it via set-index.
    Requires --site (or a configured default); --local is not supported."""
    if ctx.obj.get("remote") is None:
        click.echo("sync requires a remote site; pass --site KEY (or set a "
                   "default in sites.toml). --local is unsupported.", err=True)
        sys.exit(1)
    site_key = ctx.obj.get("site_key")
    if not site_key:
        click.echo("sync needs a registry-backed site (raw --remote without a "
                   "matching sites.toml entry is unsupported).", err=True)
        sys.exit(1)
    content_root = _content_root()
    if content_root is None:
        click.echo("Cannot locate content/: no .git/pyproject.toml ancestor of CWD.", err=True)
        sys.exit(1)
    site_dir = content_root / site_key
    if not site_dir.is_dir():
        click.echo(f"No content/{site_key}/ directory found.", err=True)
        sys.exit(1)

    remote = ctx.obj["remote"]
    remote_dir = ctx.obj["remote_dir"]

    index_entry, local_pages = _enumerate_content_site(site_dir)
    remote_pages = _remote_pages_index(remote, remote_dir)
    remote_slugs = {p["slug"]: p for p in remote_pages if "slug" in p}

    to_push   = sorted(s for s in local_pages if s not in remote_slugs)
    to_revise = sorted(s for s in local_pages if s in remote_slugs)
    # The remote's reserved root-index slug ("index") maps to the manifest's
    # index entry, not to a top-level page, so it is never remote-only.
    reserved_index_slugs = {"index"} if index_entry is not None else set()
    to_recycle = sorted(s for s in remote_slugs
                        if s not in local_pages and s not in reserved_index_slugs)

    click.echo(f"Sync plan for '{site_key}':")
    click.echo(f"  push:    {to_push or '(none)'}")
    click.echo(f"  revise:  {to_revise or '(none)'}")
    click.echo(f"  recycle: {to_recycle or '(none)'}")
    click.echo(f"  index:   {index_entry.name if index_entry else '(none)'}")
    if dry_run:
        return

    # Recycle first so we don't accidentally revise a page we're about to drop.
    bin_root: Path | None = None
    recycled_ok: list[str] = []
    if to_recycle:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
        bin_root = site_dir / RECYCLE_DIR_NAME / ts
    for slug in to_recycle:
        slug_bin = bin_root / slug
        _recycle_remote_page(remote, remote_dir, slug_bin, slug, remote_slugs[slug])
        ctx.invoke(delete, slug=slug)
        recycled_ok.append(slug)

    # An html entry's metadata lives in _pages.yaml (no frontmatter to lift), so
    # feed it back as flags; md entries carry their own frontmatter.
    def _meta_kwargs(slug: str, entry: Path) -> dict:
        if entry.suffix.lower() != ".html":
            return {}
        m = _read_pages_meta(site_key, slug)
        kw = {k: m[k] for k in ("title", "description", "theme",
                                "color_scheme", "parent", "excerpt") if m.get(k)}
        if m.get("tags"):
            kw["tags"] = tuple(m["tags"])
        return kw

    pushed_ok: list[str] = []
    for slug in to_push:
        entry = local_pages[slug]
        ctx.invoke(push, file_path=str(entry), slug=slug, **_meta_kwargs(slug, entry))
        pushed_ok.append(slug)

    revised_ok: list[str] = []
    for slug in to_revise:
        entry = local_pages[slug]
        ctx.invoke(revise, slug=slug, file_path=str(entry), **_meta_kwargs(slug, entry))
        revised_ok.append(slug)

    if index_entry:
        ctx.invoke(set_index, file_path=str(index_entry))

    click.echo()
    click.echo(f"Sync report for '{site_key}':")
    click.echo(f"  pushed   ({len(pushed_ok)}): {pushed_ok or '(none)'}")
    click.echo(f"  revised  ({len(revised_ok)}): {revised_ok or '(none)'}")
    click.echo(f"  recycled ({len(recycled_ok)}): {recycled_ok or '(none)'}")
    if bin_root is not None:
        try:
            rel = bin_root.relative_to(content_root.parent)
        except ValueError:
            rel = bin_root
        click.echo(f"  recycle bin: {rel}/")
    click.echo(f"  index:    {index_entry.name if index_entry else '(unchanged)'}")


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
    ~/.config/flubpub/sites.json and shells out to deploy.sh with the
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
    """Manage the sites registry at ~/.config/flubpub/sites.json."""


def _save_sites_config(cfg: dict) -> None:
    SITES_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    SITES_CONFIG_PATH.write_text(json.dumps(cfg, indent=2) + "\n")


@sites.command(name="set-content-root")
@click.argument("path", type=click.Path(path_type=Path))
def sites_set_content_root(path: Path):
    """Anchor the SSOT content/ tree to a fixed repo path.

    Once set, every mirroring push updates <PATH>/content/<key>/ no matter
    what directory you run flubpub from — `publish from anywhere` becomes
    literally true instead of CWD-dependent."""
    resolved = path.expanduser().resolve()
    if not resolved.is_dir():
        click.echo(f"Not a directory: {resolved}", err=True)
        sys.exit(1)
    cfg = _load_sites_config()
    cfg["content_root"] = str(resolved)
    _save_sites_config(cfg)
    click.echo(f"content_root → {resolved}")
    click.echo(f"(mirrors land in {resolved / 'content'}/<site>/)")


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
