from typer import Typer
import click, inflection, inspect

class EmpireTyper(Typer):
    
    def remote_component(self, fetch_list, fetch_details, name=None, help=None):
        def decorator(f):
            class RemoteComponentGroup(RemoteComponentGroupBase):
                @staticmethod
                def fetch_component_list():
                    return fetch_list()
                    
                @staticmethod
                def fetch_component_details(component_name):
                    return fetch_details(component_name)
                    
                @staticmethod
                def get_callback():
                    return f
            
            nonlocal name, help
            if name is None:
                name = f.__name__
            if help is None:
                help = inspect.cleandoc(inspect.getdoc(f))
            
            typer_instance = Typer(name=name, cls=RemoteComponentGroup, help=help, no_args_is_help=True,)
            self.add_typer(typer_instance)
            return f
        
        return decorator

class RemoteComponentCommand(click.Command):
    
    def __init__(self, name, component_details, callback):
        super().__init__(name, callback=callback, help=component_details.description, no_args_is_help=True)
        self.component_details = component_details
        self._normalized_option_names = dict()
        self._params = None
        
    def _normalize_and_cache_option_name(self, name):
        normalized_name = inflection.dasherize(inflection.underscore(name))
        
        # assert that there is no collision introduced by normalization
        cache_hit = self._normalized_option_names.get(normalized_name, None)
        assert cache_hit is None or name == cache_hit 
        
        # cache and return our results
        self._normalized_option_names[normalized_name] = name # cache the mapping from normalized_name -> name
        return normalized_name
    
    def _resolve_click_option_name(self, click_name):
        normalized_name = inflection.dasherize(click_name)
        return self._normalized_option_names[normalized_name]
    
    def _generate_params(self, ctx):
        opt: ListenerOption
        for opt in sorted(self.component_details.options, key=lambda x: not (x.required and not x.value)):
            normalized_name = self._normalize_and_cache_option_name(opt.name)
            option = click.Option(
                    [f"--{normalized_name}"], 
                    # required=opt.required, 
                    # default= opt.value or None, 
                    # show_default=True, 
                    help=opt.description
                )
            yield option
    
    def get_params(self, ctx):
        if not self._params:
            self._params = super().get_params(ctx)
            self._params += list(self._generate_params(ctx))
        return self._params
    
    def invoke(self, ctx):
        """Given a context, this invokes the attached callback (if it exists)
        in the right way.
        """
        if self.callback is not None:
             
            def _pimped_callback(**kwargs):
                options = dict()
                for click_name, value in kwargs.items():
                    option = self._resolve_click_option_name(click_name)
                    if value:
                        options[option] = str(value)
                self.callback(self.name, options)
            
            return ctx.invoke(_pimped_callback, **ctx.params)
    
class RemoteComponentGroupBase(click.Group):
    
    def list_commands(self, ctx):
        listener_types = ctx.invoke(self.fetch_component_list)
        return sorted(listener_types)
    
    def get_command(self, ctx, component_name):
        # TODO: Currently, the server only allows us to gather a list of component names -or- the details for a single component with one request. 
        # This forces us to query the server once for each component we want to know more about than its name alone. 
        # Maybe introduce an API endpoint which allows us to grab all high-level information about a component needed for CLI generation in one go, to lower the volume of requests. 
        return RemoteComponentCommand(component_name, component_details=self.fetch_component_details(component_name), callback=self.get_callback())
    
    @staticmethod
    def fetch_component_list():
        raise NotImplementedError()
    
    @staticmethod
    def fetch_component_details(component_name):
        raise NotImplementedError()
    
    @staticmethod
    def get_callback():
        return create