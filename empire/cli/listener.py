from typing import Optional, List
import typer
import functools, inspect
from empire.client.src.api import ServerConnection, ListenerOption, ListenerType
from empire.client.src.utils import table_util, print_util
from empire.cli import empire

app = empire.EmpireTyper()

@app.callback(invoke_without_command=True)
def _common(
        ctx: typer.Context,
    ):
    pass

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

# @app.command()
# def create(
#         ctx: typer.Context, 
#         listener_type: str, 
#         name: Optional[str] = None
#     ):
#     srv: ServerConnection = ctx.obj.empire_api
#         
#     if name is None:
#         active_listeners = srv.get_active_listeners()
#         
#     srv.create_listener(listener_type, {"Name": "test", "Port": 80})
#     typer.echo(name)

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

class CreateCommandGenerator(typer.Typer):
    """
    Auto-generated group of create commands. 
    """
    def __init__(self, listener_types: List[ListenerType]):
        super().__init__()
        commands = self._generate_commands(listener_types)
        self.registered_commands += list(commands)
    
    def _generate_commands(self, listener_types):
        for listener_type in listener_types:
            
            @functools.wraps(CreateCommandGenerator._create)
            def wrapper(*args, **kwargs):
                CreateCommandGenerator._create(*args, **kwargs)
            
            wrapper.__signature__ = self._generate_signature(listener_type)
            
            yield typer.models.CommandInfo(callback=wrapper, name=listener_type.name, help=listener_type.description)
    
    def _generate_signature(self, listener_type):
        params = []
        option: ListenerOption
        for option in sorted(listener_type.options, key=lambda x: not x.required):
            
            param_info_type = typer.Argument if (option.required and not option.value )else typer.Option
            
            param = inspect.Parameter(
                    option.name, 
                    inspect.Parameter.POSITIONAL_OR_KEYWORD, 
                    default=param_info_type(option.value, help=option.description),
                    annotation=str,
                )
            params += [param]
        return inspect.Signature(params)
            
    @staticmethod
    def _create(*args, **kwargs):
        print("hi there")
        print(args, kwargs)

print(app.empire_conf)

app.add_typer(CreateCommandGenerator([ListenerType("author", "category", "comments", "description", "lstnr", [ListenerOption("name", "description", False, "strict", "suggested_values", "value")])]), name="create")