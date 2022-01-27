import requests
from pathlib import Path
import yaml
from typing import Dict, List
from datetime import datetime
from dataclasses import dataclass

class AuthenticationToken(str):
    pass

class AuthenticationError(RuntimeError):
    pass

@dataclass
class BaseOption:
    name: str
    description: str
    required: str
    strict: str
    suggested_values: str
    value: str
    
    @classmethod
    def from_dict(cls, name, data):
        return cls(
            name,
            description = data['Description'],
            required = data['Required'], 
            strict = data['Strict'], 
            suggested_values = data['SuggestedValues'], 
            value = data['Value']
        )

@dataclass
class BaseType:
    author: str
    comments: str
    description: str
    name: str
    options: str
        
    @classmethod
    def from_dict(cls, data):
        raise NotImplementedError()
    
class ListenerOption:
    def __init__(self, name, description, required, strict, suggested_values, value):
        self.name = name
        self.description = description
        self.required = required
        self.strict = strict
        self.suggested_values = suggested_values
        self.value = value
    
    @classmethod
    def from_dict(cls, name, data):
        return cls(
            name,
            description = data['Description'],
            required = data['Required'], 
            strict = data['Strict'], 
            suggested_values = data['SuggestedValues'], 
            value = data['Value']
        )
        
class ListenerType:
    def __init__(self, author, category, comments, description, name, options):
        self.author = author
        self.category = category 
        self.comments = comments
        self.description = description 
        self.name = name
        self.options = options
    
    @classmethod
    def from_dict(cls, data):
        info = data['listenerinfo']
        options = [ListenerOption.from_dict(name, arg_dict) for name, arg_dict in data['listeneroptions'].items()]
        return cls(
            author = info['Author'],
            category = info['Category'], 
            comments = info['Comments'], 
            description = info['Description'], 
            name = info['Name'],
            options=options,
        )
        
class Listener:
    def __init__(self, id: int, name: str, type_name: str, enabled: bool, created_at: str, options: List[ListenerOption] = []):
        self.id = id
        self.name = name
        self.type_name = type_name
        self.enabled = enabled
        self.created_at = created_at
        self.options = options
    
    @classmethod
    def from_dict(cls, data):
        options = [ListenerOption.from_dict(name, arg_dict) for name, arg_dict in data['options'].items()]
        return cls(
            id = int(data['ID']),
            name = data['name'],
            type_name = data['module'],
            enabled = data['enabled'],
            created_at = data['created_at'],
            options = options,
        )


class StagerOption(BaseOption):
    pass

@dataclass
class StagerType(BaseType):
    
    @classmethod
    def from_dict(cls, data):
        options = [StagerOption.from_dict(name, arg_dict) for name, arg_dict in data['options'].items()]
        return cls(
            author = data['Author'],
            comments = data['Comments'], 
            description = data['Description'], 
            name = data['Name'],
            options=options,
        )
        

class ServerConnection:
    DEFAULT_PORT: int = 1337
    
    def __init__(self, host, port: int=DEFAULT_PORT, token: str = None):
        self.host = host
        self.port = port
        self.token = token
    
    def login(self, username: str, password: str) -> AuthenticationToken:
        response = requests.post(url=f'{self.host}:{self.port}/api/admin/login',
                                 json={'username': username, 'password': password},
                                 verify=False)
    
        if response.status_code == 200:
            self.token = AuthenticationToken(response.json()['token'])
            return self.token
    
        elif response.status_code == 401:
            raise AuthenticationError(response)
    
    def _check_response_ok(self, response):
        response_ok = False
        if response.status_code == 200:
            response_ok = True
        elif response.status_code == 401:
            raise AuthenticationError(response)
        return response_ok
    
    def _check_and_parse_response(self, response, expected_payload_type=dict, key=None):
        """
        Check for errors and if everything is ok extract the payload of the response. 
        
        You may request immediate parsing of the response, by specifying an `expected_payload_type`. 
        If the payload is a list of items, each item will be parsed individually.
        """
        if self._check_response_ok(response):
            result = None
            payload = response.json()
            if key is not None:
                payload = payload[key]
                
            if expected_payload_type is not dict:
                if isinstance(payload, list):
                    result = list()
                    for item in payload:
                        result += [
                            expected_payload_type.from_dict(item)
                        ]
                else:
                    result = expected_payload_type.from_dict(payload)
            else:
                result = payload
                
            return result
    
    def _check_and_get_status_message(self, response):
        if self._check_response_ok(response):
            status_msg = response.json()
            error = status_msg.get('error', None)
            if error:
                raise RuntimeError(status_msg['error'])
                
            success = status_msg.get('success')
            return success
    
    def get_active_listeners(self) -> List[Listener]:
        response = requests.get(url=f'{self.host}:{self.port}/api/listeners',
                                verify=False,
                                params={'token': self.token})
        
        listeners = [Listener.from_dict(x) for x in response.json()['listeners']]
        return listeners
    
    def get_listener_types(self):
        response = requests.get(url=f'{self.host}:{self.port}/api/listeners/types',
                                verify=False,
                                params={'token': self.token})
        return response.json()['types']
    
    def get_listener_details(self, listener_type: str):
        response = requests.get(url=f'{self.host}:{self.port}/api/listeners/options/{listener_type}',
                                verify=False,
                                params={'token': self.token})
        
        details_dict = self._check_and_parse_response(response)
        return ListenerType.from_dict(details_dict)
    
    def create_listener(self, listener_type: str, options: Dict):
        response = requests.post(url=f'{self.host}:{self.port}/api/listeners/{listener_type}',
                                 json=options,
                                 verify=False,
                                 params={'token': self.token})
        
        msg = self._check_and_get_status_message(response)
        return msg
    
    def kill_listener(self, listener_name: str):
        response = requests.delete(url=f'{self.host}:{self.port}/api/listeners/{listener_name}',
                                   verify=False,
                                   params={'token': self.token})
        
        msg = self._check_and_get_status_message(response)
        return msg
    
    def get_stagers(self):
        # todo need error handling in all api requests
        response = requests.get(url=f'{self.host}:{self.port}/api/stagers',
                                verify=False,
                                params={'token': self.token})
    
        self.stagers = {x['Name']: x for x in response.json()['stagers']}
    
        return self.stagers
    
    def get_stager_details(self, name: str):
        # todo need error handling in all api requests
        response = requests.get(url=f'{self.host}:{self.port}/api/stagers/{name}',
                                verify=False,
                                params={'token': self.token})
        
        result = self._check_and_parse_response(response, StagerType, key="stagers")
        
        # for same strange reason the server returns the single stager details in a list...
        result = result[0] # let's unpack it
        
        return result
    
    def create_stager(self, stager_name: str, options: Dict):
        options['StagerName'] = stager_name
        response = requests.post(url=f'{self.host}:{self.port}/api/stagers',
                                 json=options,
                                 verify=False,
                                 params={'token': self.token})
    
        return response.json()