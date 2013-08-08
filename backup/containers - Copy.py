from .enums import Netmodes
from .handler_interfaces import static_description

from copy import deepcopy
from functools import partial
from inspect import getmembers
from collections import OrderedDict

class StorageInterface:
    
    def __init__(self, getter, setter):
        self.getter = getter
        self.setter = setter
    
    @property
    def value(self):
        return self.getter()
    
    @value.setter
    def value(self, value):
        self.setter(value)
    
class AttributeStorageInterface(StorageInterface):
    def __init__(self, getter, setter, complaint):
        super().__init__(getter, setter)
        
        self.set_complaint = complaint

class AttributeContainer:
    
    def __init__(self, instance):
        self.instance = instance
        
        self._mapping = self.get_attribute_instances(instance)
        
        self.data = self.get_initialised_data(instance, self._mapping)
        self.complaints = self.get_complaint_descriptions(self.data)
        
        self._lazy_name_mapping = {}
        self._storage_interfaces = {}

    @staticmethod
    def get_initialised_data(instance, mapping):
        return {attribute: attribute.copied_value for name, attribute in mapping.items()}
    
    @staticmethod
    def get_attribute_instances(instance):
        return {name: value for name, value in getmembers(instance.__class__) if isinstance(value, Attribute)}
    
    @staticmethod
    def get_complaint_descriptions(data):
        return {attribute: static_description(value) for attribute, value in data.items()}
    
    def get_ordered_attributes(self):
        return OrderedDict((key, self._mapping[key]) for key in sorted(self._mapping))
    
    def get_attribute_by_name(self, name):
        return self._mapping[name]
    
    def get_name_by_attribute(self, attribute):
        try:
            return self._lazy_name_mapping[attribute]
        except KeyError:
            name = self._lazy_name_mapping[attribute] = next(n for n, a in self._mapping.items() if a == attribute)
            return name
    
    def register_storage_interfaces(self):
        for name, attribute in self._mapping.items():
            storage_interface = self.new_storage_interface(attribute)
            
            attribute.register(self.instance, storage_interface)
            attribute.set_name(name)
            
            self._storage_interfaces[attribute] = storage_interface
            
    def new_storage_interface(self, member):
        getter = partial(self.data.__getitem__, member)
        setter = partial(self.data.__setitem__, member)
        complain = partial(self.complaints.__setitem__, member)
        
        return AttributeStorageInterface(getter, setter, complain)
    
    def get_storage_interface(self, member):
        return self._storage_interfaces[member]
        
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
            raise TypeError("Cannot set {} value to {} value".format(self._type, type(value)))
        
        # Store value
        storage_interface.value = value
         
    def __str__(self):
        return "[Attribute] name: {}, type: {}, initial value: {}".format(self.name, self.type.__name__, self._value)
