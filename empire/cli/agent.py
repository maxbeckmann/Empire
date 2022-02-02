from typing import List

import typer, click
import tabulate
from empire.client.src.api import ServerConnection, ApiError
from empire.client.src.utils import print_util
from empire.cli import empire

app = empire.EmpireTyper()


@click.pass_context
def fetch_agent_list(ctx: typer.Context):
    srv: ServerConnection = ctx.obj.empire_api
    return srv.get_agents()


@app.callback(no_args_is_help=True)
def _common():
    """
    Interact with agents. 
    """

@app.command("ps")
@app.command("list")
def list_agents(all: bool = False):
    """
    List checked-in agents. 
    """
    agents = fetch_agent_list()
    
    headers = ["ID", "CHECK-IN", "NAME", "HOST", "USERNAME"]
    tabular_data = []
    
    for a in agents:
        if all or not a.stale:
            tabular_data += [[
                a.ID, 
                a.checkin_time,
                a.name, 
                a.hostname, 
                a.username, 
            ]]
    
    output = tabulate.tabulate(tabular_data, headers)
    typer.echo(output)
    
@app.command("kill", no_args_is_help=True)
def kill_agent(ctx: typer.Context, names: List[str]):
    srv: ServerConnection = ctx.obj.empire_api
    
    killed = []
    for name in names:
        try:
            srv.kill_agent(name)
            killed += [name]
        except ApiError as ex:
            typer.echo(f"failed to kill '{name}: {ex}'")
    
    if killed:
        typer.echo(print_util.shell_enumerate(killed))

@app.command("sh")
@app.command("shell", no_args_is_help=True)
def run_shell_on_agent(ctx: typer.Context, name: str, command: str):
    import time
    srv: ServerConnection = ctx.obj.empire_api
    
    task_id = srv.agent_shell(name, command)
    
    # TODO: Add an HTTP endpoint not returning until the result arrived from the agent. 
    # Websockets might work as well, but considering that this process will reload on each
    # invocation the additional bootstrapping might not be worthwhile. 
    result = srv.get_task_result(name, task_id)
    while result['results'] is None:
        time.sleep(0.5)
        result = srv.get_task_result(name, task_id)
    
    output = result['results']
    typer.echo(output)

@app.command("upload", no_args_is_help=True)
def upload_file(ctx: typer.Context, name: str, path: str):
    """
    Upload a file to the host running an agent. 
    """
    srv: ServerConnection = ctx.obj.empire_api
    
    with open(path, 'rb') as stream:
        data = stream.read()
    
    success = srv.agent_upload_file(name, path, data)
    assert success

@app.command("download", no_args_is_help=True)
def upload_file(ctx: typer.Context, name: str, path: str):
    """
    Download a file from the host running an agent. 
    """
    srv: ServerConnection = ctx.obj.empire_api
    
    success = srv.agent_download_file(name, path)
    assert success