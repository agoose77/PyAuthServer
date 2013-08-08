from copy import deepcopy
from functools import partial
from inspect import signature
from collections import OrderedDict

from .handler_interfaces import static_description
from .modifiers import is_simulated, simulated
from .enums import Roles
from .argument_serialiser import ArgumentSerialiser

class StaticValue:
    '''Container for static-type values
    holds type for value and additional keyword arguments
    Pretty printable'''
    __slots__ = 'type', 'data'
    
    def __init__(self, type_, **kwargs):
        self.type = type_
        self.data = kwargs
    
    def __str__(self):
        return "Static Typed value: {}".format(self.type)

class Attribute(StaticValue):
    '''Replicable attribute descriptor
    Extends Static Value, using type of initial value
    Holds additional behavioural parameters'''
    
    __slots__ = "notify", "complain", "name", "_data", "_value"
    
    def __init__(self, value=None, notify=False, complain=True, type_of=None, **kwargs):
            
        super().__init__(type_of or type(value), **kwargs)
        
        self.notify = notify
        self.complain = complain
        self.name = None
        
        self._value = value
        self._data = {}
    
    @property
    def copied_value(self):
        return deepcopy(self._value)
        
    def set_name(self, name):
        self.name = name
    
    def register(self, instance, storage_interface):
        '''Registers attribute for instance
        Stores name of attribute through search'''
        self._data[instance] = storage_interface
        
        storage_interface.value = self.copied_value
    
    def __get__(self, instance, base):        
        # Try and get value, or register to instance
        try:
            storage_interface = self._data[instance]
            return storage_interface.value
        
        except AttributeError:
            return self
    
    def __set__(self, instance, value):
        storage_interface = self._data[instance]
        
        # Get the last value
        last_value = storage_interface.value
        
        # Avoid executing unnecessary logic
        if last_value == value:
            return
        
        # If the attribute should complain 
        if self.complain:
            # Register a complain with value description
            storage_interface.set_complaint(static_description(value))
            
        # Force type check
        if not isinstance(value, self.type):
            raise TypeError("Cannot set {} value to {} value".format(self.type, type(value)))
        
        # Store value
        storage_interface.value = value
         
    def __str__(self):
        return "[Attribute] name: {}, type: {}, initial value: {}".format(self.name, self.type.__name__, self._value)

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