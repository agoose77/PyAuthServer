from itertools import chain

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
    
    def __new__(meta, name, parents, attrs):        
        cls = super().__new__(meta, name, parents, attrs)
        
        if not hasattr(cls, "_types"):
            cls._types = []
            
            if hasattr(cls, "register_type"):
                cls.register_type()
        
        else:
            cls._types.append(cls)
            
            if hasattr(cls, "register_subtype"):
                cls.register_subtype()
            
        return cls
    
    @property
    def type_name(self):
        return self.__name__
    
    def from_type_name(self, type_name):
        for cls in self._types:
            if cls.__name__ == type_name:
                return cls
        
        raise LookupError("No class with name {}".format(type_name))
        
class InstanceMixins:
    
    def __init__(self, instance_id=None, register=False, allow_random_key=False, **kwargs):
        super().__init__(**kwargs)   

        self.allow_random_key = allow_random_key

        # Add to register queue
        self.request_registration(instance_id)
        
        # Update graph
        if register:
            self.update_graph()
        
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
            return cls._instances.pop(instance_id)
        
        for i in cls._to_register:
            if i.instance_id != instance_id:
                continue
            
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
            for replicable in cls._to_register.copy():
                replicable._register_to_graph()
        
        if cls._to_unregister:   
            for replicable in cls._to_unregister.copy():
                replicable._unregister_from_graph()
        
    def request_unregistration(self, unregister=False):
        if not self.registered:
            return
        
        self.__class__._to_unregister.add(self)
        
        if unregister:
            self._unregister_from_graph()
            
    def request_registration(self, instance_id):
        if instance_id is None:
            
            if not self.allow_random_key:
                raise KeyError("No key specified")
            
            instance_id = self.get_random_id()
            
        self.instance_id = instance_id
        self.__class__._to_register.add(self) 
    
    def _register_to_graph(self):
        self.__class__._instances[self.instance_id] = self
        self.__class__._to_register.remove(self)
        self.on_registered()
        
    def _unregister_from_graph(self):
        self.__class__._instances.pop(self.instance_id)
        self.__class__._to_unregister.remove(self)
        self.on_unregistered()
        
    def on_registered(self):
        pass

    def on_unregistered(self):
        pass
    
    @property
    def registered(self):
        return self.__class__._instances.get(self.instance_id) is self
    
    def __bool__(self):
        return self.registered
    
class InstanceRegister(TypeRegister):
    
    def __new__(meta, name, parents, attrs):       
        
        parents += (InstanceMixins,) 
        cls = super().__new__(meta, name, parents, attrs)
        
        if not hasattr(cls, "_instances"):
            cls._instances = {}
            cls._to_register = set()
            cls._to_unregister = set()
                        
        return cls
    
    def __iter__(self):
        return iter(self._instances.values())
    
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
        