from .modifiers import is_simulated
from inspect import signature
from collections import OrderedDict, defaultdict

from .argument_serialiser import ArgumentSerialiser
from .descriptors import StaticValue
from .factorydict import FactoryDict

from copy import deepcopy

class RPC:
    '''Manages instances of an RPC function for each object'''
        
    def __init__(self, func):        
        self.__annotations__ = func.__annotations__
        
        self._func = func
        self._simulated = is_simulated(self)
        self._by_instance = {}
        self._replacements = {}
        
    def __get__(self, instance, base):
        if instance is None:
            return self
        
        try:
            return self._by_instance[instance]
        except KeyError:
            pass
        
    def update_class_arguments(self, func, instance):
        annotations = func.__annotations__
        
        instance_cls = instance.__class__

        for name, static_value in annotations.items():
            if not isinstance(static_value, StaticValue):
                continue
            
            replace = static_value.data.get("class_data", {})
            replace_data = self._replacements.get(name, {})
            
            for key, attr_name in replace.items():
                try:
                    value = replace_data[key]
                except KeyError:
                    value = getattr(instance_cls, attr_name)
                    replace_data[key] = value
                    
                static_value.data[key] = value
            
    def create_rpc_interface(self, instance):
        bound_func = self._func.__get__(instance)
        
        self.update_class_arguments(bound_func, instance)
        
        self._by_instance[instance] = RPCInterface(bound_func)
        return self._by_instance[instance]
                    
class RPCInterface:
    """Mediates RPC calls to/from peers"""
    
    def __init__(self, function):
        
        # Used to isolate rpc_for_instance for each function for each instance
        self._function = function
        self._function_signature = signature(function)
        
        # Information about RPC
        self.name = function.__qualname__
        self.__annotations__ = function.__annotations__
        
        # Get the function signature
        self.target = self._function_signature.return_annotation
        
        # Interface between data and bytes
        self._serialiser = ArgumentSerialiser(self.ordered_arguments(self._function_signature))
        self._binder = self._function_signature.bind
        
        from .network import WorldInfo
        self._system_netmode = WorldInfo.netmode
    
    def register(self, interface, rpc_id):
        self.rpc_id = rpc_id
        self._interface = interface
    
    def ordered_arguments(self, sig):
        return OrderedDict((value.name, value.annotation) 
                           for value in sig.parameters.values() 
                           if isinstance(value.annotation, StaticValue))
               
    def __call__(self, *args, **kwargs):
        # Determines if call should be executed or bounced
        if self.target == self._system_netmode:
            return self._function.__call__(*args, **kwargs)

        arguments = self._binder(*args, **kwargs).arguments
        data = self._serialiser.pack(arguments)
      
        self._interface.setter(data)
    
    def execute(self, bytes_):        
        # Unpack RPC
        try:
            unpacked_data = self._serialiser.unpack(bytes_)
            
        except Exception as err:
            print("Error unpacking {}: {}".format(self.name, err))
            
        # Execute function
        try:
            self._function.__call__(**dict(unpacked_data))
            
        except Exception as err:
            print("Error invoking {}: {}".format(self.name, err))
            raise