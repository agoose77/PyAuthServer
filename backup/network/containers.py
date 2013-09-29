from .handler_interfaces import static_description
from .descriptors import Attribute, RPC

from functools import partial
from collections import OrderedDict, deque
from inspect import getmembers

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

class AbstractStorageContainer:
    
    def __init__(self, instance):
        self._mapping = self.get_member_instances(instance)
        
        self.data = self.get_initialised_data(self._mapping)
        
        self._lazy_name_mapping = {}
        self._storage_interfaces = {}
        self._instance = instance
    
    def get_initial_data(self, member):
        return NotImplemented
    
    def check_is_supported(self, member):
        return NotImplemented
    
    def get_member_instances(self, instance):
        return {name: value for name, value in getmembers(instance.__class__) if self.check_is_supported(value)}

    def get_initialised_data(self, mapping):
        return {member: self.get_initial_data(member) for member in mapping.values()}
    
    def get_ordered_members(self):
        return OrderedDict((key, self._mapping[key]) for key in sorted(self._mapping))
    
    def get_member_by_name(self, name):
        return self._mapping[name]
    
    def get_name_by_member(self, member):
        try:
            return self._lazy_name_mapping[member]
        except KeyError:
            name = self._lazy_name_mapping[member] = next(n for n, a in self._mapping.items() if a == member)
            return name
    
    def register_storage_interfaces(self):
        for name, member in sorted(self._mapping.items()):            
            self._storage_interfaces[member] = self.new_storage_interface(name, member)
    
    def new_storage_interface(self, name, member):
        return StorageInterface(*self.get_storage_accessors(member))
    
    def get_storage_accessors(self, member):
        getter = partial(self.data.__getitem__, member)
        setter = partial(self.data.__setitem__, member)
        return getter, setter
    
    def get_storage_interface(self, member):
        return self._storage_interfaces[member]

class RPCStorageContainer(AbstractStorageContainer):
    
    def __init__(self, instance):
        super().__init__(instance)
        
        self.functions = []
    
    def check_is_supported(self, member):
        return isinstance(member, RPC)
    
    def get_initialised_data(self, mapping):
        return deque()
    
    def _add_call(self, member, value):
        self.data.append((member, value))
    
    def _add_function(self, func):
        self.functions.append(func)
        return self.functions.index(func)
    
    def new_storage_interface(self, name, member):
        adder = partial(self._add_call, member)
        interface = RPCStorageInterface(adder)
        
        member.register(self._instance, interface, self._add_function)
        
        return interface

class AttributeStorageContainer(AbstractStorageContainer):
    
    def __init__(self, instance):
        super().__init__(instance)
        
        self.complaints = self.get_complaint_descriptions(self.data)

    def get_complaint_descriptions(self, data):
        return {attribute: static_description(value) for attribute, value in data.items()}
    
    def check_is_supported(self, member):
        return isinstance(member, Attribute)
    
    def get_initial_data(self, attribute):
        return attribute.value
    
    def new_storage_interface(self, name, member):
        getter, setter = self.get_storage_accessors(member)
        
        complain_setter = partial(self.complaints.__setitem__, member)
        interface = AttributeStorageInterface(getter, setter, complain_setter)
        
        member.register(self._instance, interface)
        member.name = name
        
        return member

class RPCStorageInterface(StorageInterface):
    
    def __init__(self, setter):
        super().__init__(object, setter)

class AttributeStorageInterface(StorageInterface):
    
    def __init__(self, getter, setter, complaint):
        super().__init__(getter, setter)
        
        self.set_complaint = complaint

        
