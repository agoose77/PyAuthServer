from .modifiers import is_simulated
from inspect import signature
from collections import OrderedDict

from .argument_serialiser import ArgumentSerialiser
from .descriptors import StaticValue

class RPC:
    '''Manages instances of an RPC function for each object'''
        
    def __init__(self, func):        
        self.__annotations__ = func.__annotations__
        
        self._func = func
        self._simulated = is_simulated(self)
        self._by_instance = {}
    
    def __get__(self, instance, base):
        try:
            return self._by_instance[instance]
        
        except KeyError:
            return None
        
    def register(self, instance, interface, register_function):
        bound_function = self._func.__get__(instance, None)
        
        rpc_interface = RPCInterface(interface, bound_function, register_function)
        self._by_instance[instance] = rpc_interface
            
class RPCInterface:
    """Mediates RPC calls to/from peers"""
    
    def __init__(self, interface, function, get_rpc_id):
        
        # Used to isolate rpc_for_instance for each function for each instance
        self._function = function
        self._function_signature = signature(function)
        
        self.rpc_id = get_rpc_id(self)
        self.name = function.__qualname__
        self.__annotations__ = function.__annotations__
        
        # Get the function signature
        self.target = self._function_signature.return_annotation
        
        # Interface between data and bytes
        self._serialiser = ArgumentSerialiser(self.ordered_arguments(self._function_signature))
        self._binder = self._function_signature.bind
        self._interface = interface
        
        from .network import WorldInfo
        self._system_netmode = WorldInfo.netmode
    
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