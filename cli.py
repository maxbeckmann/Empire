#!/usr/bin/env python3
import typer, urllib3
from typing import Optional
from dataclasses import dataclass
from empire.client.src import api
from empire.client.src.config import Config, Path
from empire.cli import listener

app = typer.Typer()
app.add_typer(listener.app, name="listener")


def _get_invocation_name():
    return Path(__file__).name


class TokenFile:
    def __init__(self, location: Path = Path(".connection")):
        self.location = location
    
    def load(self) -> str:
        result = None
        if self.location.exists():
            with open(self.location, 'r') as stream:
                result =  stream.read()
        return result
        
    def store(self, token: str):
        with open(self.location, 'w') as stream:
            stream.write(token)
    
    def remove(self):
        self.location.unlink()

@dataclass
class State:
    empire_conf: Config
    empire_api: api.ServerConnection

@app.command()
def login(
        ctx: typer.Context,
        username: str = typer.Option(None, envvar='EMPIRE_USER', help='Name of the user to login'),
        password: str = typer.Option(None, help='Password of the user to login', prompt=True, hide_input=True),
    ):
    """
    Login to the Empire teamserver. 
    An API request token will be obtained when given a valid pair of username and password. 
    """
    
    if username is None:
        server_config = ctx.obj.empire_conf.get_active_profile()
        username = server_config['username']
    
    try:
        empire_api = ctx.obj.empire_api
        token = empire_api.login(username, password)
        
        # store connection details and credentials for future invocations
        TokenFile().store(token)
        
        typer.echo(f"Logged in as '{username}'.")
    except api.AuthenticationError:
        typer.echo("Failed. Did you enter the correct password?")
        raise typer.Exit(1)

@app.command()
def logout():
    TokenFile().remove()
    typer.echo("OK")
    

@app.callback(invoke_without_command=True)
def _common(
        ctx: typer.Context,
        token: str = typer.Option(None, envvar='EMPIRE_TOKEN', help='Empire server access token'),
        host: str = typer.Option(None, envvar='EMPIRE_HOST', help='Empire server URL'),
        port: int = typer.Option(None, envvar='EMPIRE_PORT', help='Empire server REST API port'),
        config: str = "./empire/client/config.yaml",
        server: Optional[str] = None
    ):
    """
    Shell-based Empire CLI frontend. 
    """
    
    empire_conf = Config(location=Path(config), active_profile=server) # load the config file and add it to the context
    
    if empire_conf.yaml.get('suppress-self-cert-warning', True):
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    # check wether we need to gather connection details from the config
    if host is None or port is None:
        try:
            server_config = empire_conf.get_active_profile()
        except KeyError:
            typer.echo(f"Found multiple server profiles in config '{config}'. Use --server to choose one or provide '--host' and '--port' appropriately.")
            raise typer.Abort()
    
    # use user-provided connection details, but fall back to config if some is lacking
    host = server_config['host'] if host is None else host
    port = server_config['port'] if port is None else port
    
    if token is None:
        token = TokenFile().load()
    
    empire_api = api.ServerConnection(host, port, token)
    
    ctx.obj = State(empire_conf, empire_api)


if __name__ == '__main__':
    try:
        app() 
    except api.AuthenticationError as ex:
        typer.echo(f"Authentication error. Try '{_get_invocation_name()} connect --help' for further advice.")
    except RuntimeError as ex:
        typer.echo(f"error: {ex}")    