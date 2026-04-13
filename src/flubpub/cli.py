import click


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
    click.echo("push not yet implemented")


@cli.command(name="list")
@click.pass_context
def list_pages(ctx):
    """List published pages."""
    click.echo("list not yet implemented")
