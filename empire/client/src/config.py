from typing import Dict
from pathlib import Path
import yaml

class Config(object):
    def __init__(self, location: Path= Path("./empire/client/config.yaml"), active_profile=None):
        self.location = None
        self.yaml: Dict = {}
        self.active_profile = active_profile
        self.load(location)

    def load(self, location: Path):
        with open(location, 'r') as stream:
            self.yaml = yaml.safe_load(stream)
            self.location = location
    
    def get_active_profile(self):
        profile_list = self.yaml['servers']
        server_profile = None
        if self.active_profile is None:
            if len(profile_list) > 1:
                for profile in profile_list.values():
                    if profile['autoconnect'] == True:
                        server_profile = profile
                        break
                if server_profile is None:
                    raise KeyError("There are multiple connection profiles.")
            else:
                server_profile = profile_list[0]
        else:
            server_profile = profile_list[self.active_profile]
        
        return server_profile
