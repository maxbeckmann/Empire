import typer, click, base64
from pathlib import Path
from empire.client.src.api import ServerConnection
from empire.client.src.utils import print_util
from empire.cli import empire

import tabulate

app = empire.EmpireTyper()

@click.pass_context
def fetch_stager_list(ctx):
    srv: ServerConnection = ctx.obj.empire_api
    return srv.get_stagers()

@click.pass_context
def fetch_stager_details(ctx, stager_name):
    srv: ServerConnection = ctx.obj.empire_api
    return srv.get_stager_details(stager_name)

@app.callback(no_args_is_help=True)
def _common(
        ctx: typer.Context,
    ):
    """
    List and instantiate stagers. 
    """

@app.command("ls")
@app.command("list")
def list_stagers(ctx: typer.Context,):
    """
    Enumerate available stagers. 
    """
    stagers = fetch_stager_list()
    output = print_util.shell_enumerate(stagers)
    typer.echo(output)

@app.remote_component(fetch_stager_list, fetch_stager_details, name="create")
def instantiate_stager(ctx: typer.Context, name: str, options):
    """
    Create and download a new stager instance. 
    """
    srv: ServerConnection = ctx.obj.empire_api
    result = srv.create_stager(name, options)
    stager = base64.b64decode(result[name]['Output'])
    
    out_file = options.get('OutFile', None)
    if out_file is None:
        typer.echo(stager)
    else:
        out_path = Path(out_file).absolute()
        with open(out_path, 'wb') as stream:
            stream.write(stager)
        typer.echo(f"{name}: {out_path}")