from .network import WorldInfo
from .modifiers import simulated, is_simulated
from .argument_serialiser import ArgumentSerialiser
from .containers import StaticValue
from .enums import Roles
from .registers import InstanceRegister

from inspect import signature
from collections import OrderedDict

class RPC(metaclass=InstanceRegister):
    '''Manages instances of an RPC function for each object'''
        
    def __init__(self, func):
        super().__init__()
        
        self.func = func
        self.parents = {}
        self.__annotations__ = func.__annotations__
    
    def __get__(self, instance, base):
        try:
            return self.parents[instance]
        
        except KeyError:
            if instance is None:
                return None
            
            bound_function = self.func.__get__(instance, None)
            rpc_instance = self.parents[instance] = simulated(RPCInterface(self.instance_id, instance, bound_function))
            return rpc_instance
        
class RPCInterface:
    """Mediates RPC calls to/from peers"""
    
    def __init__(self, parent_id, instance, bound_function):
        # Used to isolate rpc_for_instance for each function for each instance
        self._function = bound_function
        self._function_signature = signature(bound_function)
        self._instance = instance
        
        self.name = bound_function.__qualname__
        self.instance_id = parent_id
        self.__annotations__ = bound_function.__annotations__
        
        # Get the function signature
        self.target = self._function_signature.return_annotation
        
        # Interface between data and bytes
        self.serialiser = ArgumentSerialiser(self.ordered_arguments(self._function_signature))
        self.binder = self._function_signature.bind
        
        # Enable modifier lookup
        self.instance._rpc_functions.append(self)
    
    def ordered_arguments(self, sig):
        return OrderedDict((value.name, value.annotation) 
                           for value in sig.parameters.values() 
                           if isinstance(value.annotation, StaticValue))
               
    def __call__(self, *args, **kwargs):
        # Determines if call should be executed or bounced
        if self.target == WorldInfo.netmode:
            return self._function.__call__(*args, **kwargs)

        arguments = self.binder(*args, **kwargs).arguments
        data = self.serialiser.pack(arguments)
      
        self._instance._calls.append((self, data))
    
    def execute(self, bytes_):
        # Get object network role
        local_role = self._instance.roles.local
        simulated_role = Roles.simulated_proxy

        # Check if we haven't any authority
        if local_role < simulated_role:
            return
        
        # Or if we need special privileges
        elif local_role == simulated_role and not is_simulated(self):
            return
        
        # Unpack RPC
        try:
            unpacked_data = self.serialiser.unpack(bytes_)
        except Exception as err:
            print("Error unpacking {}: {}".format(self.name, err))
            
        # Execute function
        try:
            self.func(**dict(unpacked_data))
        except Exception as err:
            print("Error invoking {}: {}".format(self.name, err))
            raise
     