import sys
import json
import click
import httpx
from pathlib import Path


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
@click.pass_context
def push(ctx, file_path, title, slug):
    """Push a file to the server as a published page."""
    path = Path(file_path)
    content = path.read_text()

    if not title:
        title = path.stem.replace("-", " ").replace("_", " ").title()

    suffix = path.suffix.lower()
    content_type = "markdown" if suffix == ".md" else "html"

    body = {"title": title, "content": content, "content_type": content_type}
    if slug:
        body["slug"] = slug

    with httpx.Client() as client:
        resp = client.post(f"{ctx.obj['server']}/api/pages", json=body)

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
@click.pass_context
def revise(ctx, slug, file_path, title):
    """Update an existing page with new content."""
    path = Path(file_path)
    content = path.read_text()
    suffix = path.suffix.lower()
    content_type = "markdown" if suffix == ".md" else "html"

    body = {"content": content, "content_type": content_type}
    if title:
        body["title"] = title

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
