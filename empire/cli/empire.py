from typer import Typer
from pathlib import Path
from empire.client.src.api import ServerConnection
from empire.client.src.config import Config

class TokenFile:
    def __init__(self, location: Path = Path(".connection")):
        self.location = location
    
    def load(self) -> str:
        with open(self.location, 'r') as stream:
            return stream.read()
            
    def store(self, token: str):
        with open(self.location, 'w') as stream:
            stream.write(token)

class EmpireTyper(Typer):
    
    empire_conf: Config = None
    empire_api: ServerConnection = None
    
    def __init__(self):
        super().__init__()
        if self.empire_api is None:
            self._restore_api_connection()
            
    def _restore_api_connection(self):
        token = TokenFile().load()
        #self.empire_api = ServerConnection(host, port, token)