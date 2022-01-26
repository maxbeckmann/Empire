from typing import Optional, List
import typer
import functools, inspect
from empire.client.src.api import ServerConnection, ListenerOption, ListenerType
from empire.client.src.utils import table_util, print_util
from empire.cli import empire

app = typer.Typer()

@app.callback(invoke_without_command=True)
def _common(
        ctx: typer.Context,
    ):
    """
    Manage and interact with listeners. 
    """

args = [typer.Option("foo"), typer.Option("bar")]

@app.command()
def active(ctx: typer.Context, all: bool = False):
    """
    Enumerate all active listeners. 
    """
    srv: ServerConnection = ctx.obj.empire_api
    active_listeners = srv.get_active_listeners()
    if not all:
        active_listeners = filter(lambda x: x.enabled == True, active_listeners)
    output = print_util.shell_enumerate(sorted(map(lambda x:x.name, active_listeners)))
    typer.echo(output)

@app.command()
def ps(ctx: typer.Context, all: bool = False):
    """
    Shortcut for 'active'.
    """
    active(ctx, all)

@app.command("list")
def list_listener_types(ctx: typer.Context,):
    """
    Enumerate available listener types. 
    """
    srv: ServerConnection = ctx.obj.empire_api
    listener_types = srv.get_listener_types()
    output = print_util.shell_enumerate(sorted(listener_types))
    typer.echo(output)

@app.command()
def ls(ctx: typer.Context,):
    """
    Schortcut for 'list'. 
    """
    list_listener_types(ctx)

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

import click, inflection

class RemoteCommand(click.Command):
    
    def __init__(self, name):
        super().__init__(name)
        self._normalized_option_names = dict()
        self._params = None
        self.callback = self._generate_callback()
    
    def _generate_callback(self):
        return click.pass_context(self.create)
    
    def _normalize_and_cache_option_name(self, name):
        normalized_name = inflection.dasherize(inflection.underscore(name))
        cache_hit = self._normalized_option_names.get(normalized_name, None)
        assert cache_hit is None or name == cache_hit # assert that there is no collision introduced by normalization
        
        self._normalized_option_names[normalized_name] = name # cache the mapping from normalized_name -> name
        return normalized_name
    
    def _resolve_click_option_name(self, click_name):
        normalized_name = inflection.dasherize(click_name)
        return self._normalized_option_names[normalized_name]
    
    def create(
        self,
        ctx: typer.Context, 
        name, 
        **kwargs
    ):
        srv: ServerConnection = ctx.obj.empire_api
        
        options = {"Name": name}
        for click_name, value in kwargs.items():
            option = self._resolve_click_option_name(click_name)
            if value:
                options[option] = str(value)
        
        srv.create_listener(self.name, options)
        typer.echo(name)
    
    def _fetch_remote_params(self, ctx):
        rv = []
        
        srv: ServerConnection = ctx.obj.empire_api
        listener_type = srv.get_listener_details(self.name)
        
        opt: ListenerOption
        for opt in sorted(listener_type.options, key=lambda x: not (x.required and not x.value)):
            
            normalized_name = self._normalize_and_cache_option_name(opt.name)
            # print(opt.name, repr(opt.value))
            option = click.Option(
                    [f"--{normalized_name}"], 
                    # required=opt.required, 
                    # default= opt.value or None, 
                    # show_default=True, 
                    help=opt.description
                )
            rv += [option]
            
        help_option = self.get_help_option(ctx)
        if help_option is not None:
            rv = rv + [help_option]
        return rv
    
    def get_params(self, ctx):
        if not self._params:
            self._params = self._fetch_remote_params(ctx)
        return self._params
        
class RemoteGroup(click.Group):
    
    def list_commands(self, ctx):
        srv: ServerConnection = ctx.obj.empire_api
        listener_types = srv.get_listener_types()
        return sorted(listener_types)
    
    def get_command(self, ctx, cmd_name):
        return RemoteCommand(cmd_name)

app.add_typer(
    typer.Typer(
            name="create", 
            cls=RemoteGroup, 
            help="Create a new listener instance."
        )
    )