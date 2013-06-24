from .bases import StaticValue
from .enums import Netmodes

from copy import deepcopy
from inspect import getmembers
from .handler_interfaces import static_description

class Attribute(StaticValue):
    '''Replicable attribute descriptor
    Extends Static Value, using type of initial value
    Holds additional behavioural parameters'''
    
    __slots__ = "value", "notify", "complain", "_name", "_instance"
    
    def __init__(self, value=None, notify=False, complain=True, type_of=None, **kwargs):
        if type_of is None:
            type_of = type(value)
            
        super().__init__(type_of, **kwargs)
        
        self.value = value
        self.notify = notify
        self.complain = complain
        
        self._name = None
        self._instance = None
        
    def _get_name(self, instance):
        '''Finds name of self on instance'''
        return next(name for (name, value) in getmembers(instance.__class__) if value is self)
        
    def __register__(self, instance):
        '''Registers attribute for instance
        Stores name of attribute through search'''
        self._name = self._get_name(instance)
        value = instance._data[self._name] = deepcopy(self.value)
        return value
        
    def __get__(self, instance, base):        
        # Try and get value, or register to instance
        try:
            return instance._data[self._name]
        except KeyError:
            return self.__register__(instance)
        except AttributeError:
            return self
    
    def __set__(self, instance, value):
        last_value = self.__get__(instance, None)
        
        # Avoid executing unneccesary logic
        if last_value == value:
            return
        
        # If the attribute should complain 
        if self.complain:
            # Register a complain with value description
            instance._complain[self._name] = static_description(value)
        
        from .network import WorldInfo
        
        # Force type check
        if not isinstance(value, self._type) and WorldInfo.netmode == Netmodes.server:
            raise TypeError("Cannot set {} value to {} value".format(self._type, type(value)))
        
        # Store value
        instance._data[self._name] = value
         
    def __str__(self):
        return "[Attribute] name: {}, type: {}, initial value: {}".format(self._name, self._type.__name__, self.value)
