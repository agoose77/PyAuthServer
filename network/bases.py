from copy import deepcopy
from inspect import getmembers
from itertools import chain
from .handler_interfaces import static_description

class Enum(type):
    '''Metaclass for Enums in Python'''
    def __new__(cls, name, parents, attrs):
        # Set all name to index mappings
        for index, value in enumerate(attrs["values"]):
            attrs[value] = index
        # Return new class
        return super().__new__(cls, name, parents, attrs)
           
    def __getitem__(self, index):
        # Add ability to lookup name
        return self.values[index]

class TypeRegister(type):
    '''Registers all subclasses of parent class
    Stores class name: class mapping on parent._types'''
    _register = {}
    
    def __new__(cls, name, parents, attrs):
        attrs["of_type"] = cls.of_type
        
        cls = super().__new__(cls, name, parents, attrs)

        if set(cls.__bases__).difference((object,)):
            cls._types[name] = cls
            
        return cls
    
    @staticmethod
    def of_type(self, type):
        return self.__class__._types.get(type)

class InstanceRegister:
    _instances = {}
    
    _to_register = set()
    _to_unregister = set()
    
    def __init__(self, instance_id, register=False, allow_random_key=False):        
        self.allow_random_key = allow_random_key
        
        # Add to register queue
        self.request_registration(instance_id)
        
        # Update graph
        if register:
            self.update_graph()
    
    def __del__(self):
        self.request_unregistration()
       
    @classmethod
    def get_entire_graph_ids(cls):
        instances = chain(cls._instances.keys(), (i.instance_id for i in cls._to_register))
        return instances
    
    @classmethod
    def get_graph_instances(cls, only_real=True):
        if only_real:
            return cls._instances.values()
        return chain(cls._instances.values(), cls._to_register)
     
    @classmethod
    def get_from_graph(cls, instance_id, only_real=True):
        try:
            return cls._instances[instance_id]
        except KeyError:
            # If we don't want the other values
            if only_real:
                raise LookupError
            
            try:
                return next(i for i in cls._to_register if i.instance_id==instance_id)
            except StopIteration:
                raise LookupError
            
    @classmethod
    def remove_from_entire_graph(cls, instance_id):
        if instance_id in cls._instances:
            return cls._instance.pop(instance_id)
        
        for i in cls._to_register:
            if i.instance_id == instance_id:
                cls._to_register.remove(i)
                return i
    
    @classmethod
    def get_random_id(cls):
        all_instances = list(cls.get_entire_graph_ids())
        
        for key in range(len(all_instances) + 1):
            if not key in all_instances:
                return key
    
    @classmethod
    def update_graph(cls):
        if cls._to_register:
            for replicable in cls._to_register:
                replicable._register_to_graph()
            cls._to_register.clear()
        
        if cls._to_unregister:   
            for replicable in cls._to_unregister:
                replicable._unregister_from_graph()
            cls._to_unregister.clear()    
    
    def request_unregistration(self):
        self.__class__._to_unregister.add(self)
    
    def request_registration(self, instance_id):
        if instance_id is None:
            if not self.allow_random_key:
                raise KeyError("No key specified")
            instance_id = self.get_random_id()
        
        self.instance_id = instance_id
        self.__class__._to_register.add(self) 
    
    def _register_to_graph(self):
        self.__class__._instances[self.instance_id] = self
        
    def _unregister_from_graph(self):
        self.__class__._instances.pop(self.instance_id)
    
    def on_registered(self):
        pass
    
    def on_unregistered(self):
        pass
    
    @property
    def registered(self):
        return self.instance_id in self.__class__._instances
    
class StaticValue:
    '''Container for static-type values
    holds type for value and additional keyword arguments
    Pretty printable'''
    __slots__ = '_type', '_kwargs'
    
    def __init__(self, type_, **kwargs):
        self._type = type_
        self._kwargs = kwargs
    
    def __str__(self):
        return "Static Typed value: {}".format(self._type)
        
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
        
        # Force type check
        if not isinstance(value, self._type):
            raise TypeError("Cannot set {} value to {} value".format(self._type, type(value)))
        
        # Store value
        instance._data[self._name] = value
         
    def __str__(self):
        return "[Attribute] name: {}, type: {}, initial value: {}".format(self._name, self._type.__name__, self.value)
