from typing import Optional, List
import typer, click
from empire.client.src.api import ServerConnection, ListenerOption, ListenerType
from empire.client.src.utils import table_util, print_util
from empire.cli import empire

import tabulate

app = empire.EmpireTyper()

@click.pass_context
def fetch_listener_type_list(ctx):
    srv: ServerConnection = ctx.obj.empire_api
    return srv.get_listener_types()

@click.pass_context
def fetch_listener_type_details(ctx, name):
    srv: ServerConnection = ctx.obj.empire_api
    return srv.get_listener_details(name)


@app.callback(no_args_is_help=True)
def _common(
        ctx: typer.Context,
    ):
    """
    Manage listeners. 
    """

@app.command("ps")
@app.command("active")
def list_running_listeners(ctx: typer.Context, all: bool = False):
    """
    Enumerate all active listeners. 
    """
    srv: ServerConnection = ctx.obj.empire_api
    active_listeners = srv.get_active_listeners()
    if not all:
        active_listeners = filter(lambda x: x.enabled == True, active_listeners)
    
    headers = ["ID", "CREATED", "TYPE", "NAME", ]
    tabular_data = []
    
    for l in active_listeners:
        tabular_data += [[
            l.id, 
            l.created_at,
            l.type_name, 
            l.name, 
        ]]
    
    output = tabulate.tabulate(tabular_data, headers)
    typer.echo(output)

@app.command("ls")
@app.command("list")
def list_listener_types(ctx: typer.Context,):
    """
    Enumerate available listener types. 
    """
    listener_types = fetch_listener_type_list()
    output = print_util.shell_enumerate(sorted(listener_types))
    typer.echo(output)

@app.command()
def args(
        ctx: typer.Context, 
        name: str, 
        arg: Optional[str] = None, 
        required: bool = False, 
        value: bool = False
    ):
    srv: ServerConnection = ctx.obj.empire_api
    
    result = srv.get_listener_details(name)
    arguments = result.options
    
    if arg is None:
        headers = ["NAME", "REQUIRED", "VALUE",]
        table = [headers]
        for argument in sorted(arguments, key=lambda x: not x.required):
            table += [[
                argument.name,
                argument.required,
                argument.value,
            ]]
        table_util.print_table(table)
    else:
        filtered_args = [argument for argument in arguments if argument.name == arg]
        if len(filtered_args) == 1:
            selected_arg = filtered_args[0]
            print(selected_arg)
        else: # len(filtered_args) == 0
            typer.echo(f"Unknown listener argument '{arg}'")
            raise typer.Exit(1)

@app.command()
def remove(
        ctx: typer.Context, 
        listener_name: str
    ):
    srv: ServerConnection = ctx.obj.empire_api
    status = srv.kill_listener(listener_name)
    typer.echo(listener_name)

@app.command()
def start(
        ctx: typer.Context, 
        listener_name: str
    ):
    pass

@app.command()
def stop(
        ctx: typer.Context, 
        listener_name: str
    ):
    pass

@app.remote_component(fetch_listener_type_list, fetch_listener_type_details)
def create(
        ctx: typer.Context, 
        listener_type: str, 
        options,
    ):
    """
    Create a new listener instance.
    """
    
    srv: ServerConnection = ctx.obj.empire_api
    msg = srv.create_listener(listener_type, options)
    typer.echo(options['Name'])