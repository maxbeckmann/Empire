import requests
from pathlib import Path
import yaml
from typing import Dict, List
from datetime import datetime

class AuthenticationToken(str):
    pass

class AuthenticationError(RuntimeError):
    pass

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
        if response.status_code == 401:
            raise AuthenticationError(response)
        else:
            response_ok = True
        
        return response_ok
    
    def _check_and_parse_response(self, response, expected_payload_type=dict):
        if self._check_response_ok(response):
            payload = expected_payload_type(**(response.json()))
            return payload
    
    def _check_and_get_status_message(self, response):
        if self._check_response_ok(response):
            status_msg = response.json()
            error = status_msg.get('error', None)
            if error:
                raise RuntimeError(status_msg['error'])
                
            success = status_msg.get('success')
            return success
    
    def get_active_listeners(self):
        response = requests.get(url=f'{self.host}:{self.port}/api/listeners',
                                verify=False,
                                params={'token': self.token})
        
        print(response.json())
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