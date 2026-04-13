import re
import sys
import json
import click
import httpx
from pathlib import Path


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9-]+", "", text.lower().replace(" ", "-"))


IMG_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)]+\.md)\)")


def scan_local_refs(md_path: Path) -> tuple[list[Path], list[Path]]:
    content = md_path.read_text()
    base = md_path.parent
    images, linked = [], []
    for _, src in IMG_RE.findall(content):
        if src.startswith(("http://", "https://")):
            continue
        p = (base / src).resolve()
        if p.is_file():
            images.append(p)
    for _, href in LINK_RE.findall(content):
        if href.startswith(("http://", "https://")):
            continue
        p = (base / href).resolve()
        if p.is_file():
            linked.append(p)
    return images, linked


def collect_all_refs(entry_path: Path) -> tuple[list[Path], list[Path]]:
    visited: set[Path] = set()
    all_images: list[Path] = []
    all_linked: list[Path] = []
    image_set: set[Path] = set()
    linked_set: set[Path] = set()

    def _walk(p: Path):
        rp = p.resolve()
        if rp in visited:
            return
        visited.add(rp)
        imgs, links = scan_local_refs(p)
        for img in imgs:
            if img not in image_set:
                image_set.add(img)
                all_images.append(img)
        for lnk in links:
            if lnk not in linked_set:
                linked_set.add(lnk)
                all_linked.append(lnk)
            _walk(lnk)

    _walk(entry_path)
    # Remove the entry file itself from linked list
    entry_resolved = entry_path.resolve()
    all_linked = [p for p in all_linked if p != entry_resolved]
    return all_images, all_linked


def rewrite_refs(content: str, slug: str, image_paths: list[Path], linked_mds: list[Path]) -> str:
    img_map = {p: f"/assets/{slug}/{p.name}" for p in image_paths}
    link_map = {p: f"/{_slugify(p.stem)}/" for p in linked_mds}

    def replace_img(m):
        alt, src = m.group(1), m.group(2)
        # Try to match against known image paths
        for orig, rewritten in img_map.items():
            if orig.name == Path(src).name:
                return f"![{alt}]({rewritten})"
        return m.group(0)

    def replace_link(m):
        text, href = m.group(1), m.group(2)
        for orig, rewritten in link_map.items():
            if orig.name == Path(href).name:
                return f"[{text}]({rewritten})"
        return m.group(0)

    content = IMG_RE.sub(replace_img, content)
    content = LINK_RE.sub(replace_link, content)
    return content


@click.group()
@click.option("--server", default="http://localhost:8000", show_default=True, help="Server base URL")
@click.pass_context
def cli(ctx, server):
    ctx.ensure_object(dict)
    ctx.obj["server"] = server


@cli.command()
@click.argument("file_path")
@click.option("--title", default=None, help="Page title")
@click.option("--slug", default=None, help="URL slug")
@click.option("--theme", default=None, help="Theme name (geocities, academic, hacker, angelfire, web-ring)")
@click.pass_context
def push(ctx, file_path, title, slug, theme):
    """Push a file to the server as a published page."""
    path = Path(file_path)
    content = path.read_text()

    if not title:
        title = path.stem.replace("-", " ").replace("_", " ").title()

    suffix = path.suffix.lower()
    content_type = "markdown" if suffix == ".md" else "html"

    page_slug = slug or _slugify(title)
    images, linked_mds = [], []

    if suffix == ".md":
        images, linked_mds = collect_all_refs(path)
        if images or linked_mds:
            click.echo("Local references found:")
            if images:
                click.echo("  Images:")
                for img in images:
                    click.echo(f"    ./{img.relative_to(path.parent.resolve())}")
            if linked_mds:
                click.echo("  Linked pages:")
                for md in linked_mds:
                    click.echo(f"    ./{md.relative_to(path.parent.resolve())}")
            click.echo()
            click.confirm("These files will be uploaded. Continue?", abort=True)

    server = ctx.obj["server"]
    with httpx.Client() as client:
        # Upload assets first
        for img in images:
            with open(img, "rb") as f:
                resp = client.post(
                    f"{server}/api/assets/{page_slug}",
                    files={"file": (img.name, f)},
                )
            if not resp.is_success:
                click.echo(f"Error uploading {img.name}: {resp.text}", err=True)
                sys.exit(1)
            click.echo(f"Uploaded asset: {img.name}")

        # Push linked pages first
        for md in linked_mds:
            linked_title = md.stem.replace("-", " ").replace("_", " ").title()
            linked_slug = _slugify(md.stem)
            linked_content = md.read_text()
            # Rewrite refs in linked pages too
            sub_imgs, sub_links = scan_local_refs(md)
            linked_content = rewrite_refs(linked_content, linked_slug, sub_imgs, sub_links)
            resp = client.post(
                f"{server}/api/pages",
                json={"title": linked_title, "content": linked_content, "slug": linked_slug, "content_type": "markdown"},
            )
            if not resp.is_success:
                click.echo(f"Error pushing {md.name}: {resp.text}", err=True)
                sys.exit(1)
            click.echo(f"Pushed linked page: {linked_slug}")

        # Rewrite refs in main content and push
        if images or linked_mds:
            content = rewrite_refs(content, page_slug, images, linked_mds)

        body = {"title": title, "content": content, "content_type": content_type}
        if slug:
            body["slug"] = slug
        if theme:
            body["theme"] = theme

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
@click.pass_context
def revise(ctx, slug, file_path, title, theme):
    """Update an existing page with new content."""
    path = Path(file_path)
    content = path.read_text()
    suffix = path.suffix.lower()
    content_type = "markdown" if suffix == ".md" else "html"

    body = {"content": content, "content_type": content_type}
    if title:
        body["title"] = title
    if theme:
        body["theme"] = theme

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
    with httpx.Client() as client:
        resp = client.delete(f"{ctx.obj['server']}/api/pages/{slug}")

    if resp.is_success:
        click.echo(f"Deleted: {slug}")
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
