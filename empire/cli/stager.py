from typing import Optional, List
import typer
from empire.client.src.api import ServerConnection
from empire.client.src.utils import print_util

import tabulate

app = typer.Typer()

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
    srv: ServerConnection = ctx.obj.empire_api
    stagers = srv.get_stagers()
    output = print_util.shell_enumerate(stagers)
    typer.echo(output)

@app.command("create", no_args_is_help=True)
def instantiate_stager(ctx: typer.Context, name: str):
    """
    Create and download a stager instance. 
    """
    srv: ServerConnection = ctx.obj.empire_api
    result = srv.get_stager_details(name)
    print(result)
    exit()
    result = srv.create_stager(name, {})
    print(result)
    typer.echo(listener_types)