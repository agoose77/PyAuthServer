from itertools import chain
from types import FunctionType
from functools import wraps

from .modifiers import is_simulated
from .enums import Roles, Netmodes
from .rpc import RPC

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

class InstanceNotifier:
    
    def notify_registration(self, instance):
        pass
    
    def notify_unregistration(self, instance):
        pass

class InstanceMixins:
    
    def __init__(self, instance_id=None, register=False, allow_random_key=False, **kwargs):
        super().__init__(**kwargs)   

        self.allow_random_key = allow_random_key

        # Add to register queue
        self.request_registration(instance_id)
        
        # Update graph
        if register:
            self.__class__.update_graph()
        
        # Run clean init function
        if hasattr(self, "on_initialised"):
            try:
                self.on_initialised()
            except Exception as err:
                print(err)
        
    def request_unregistration(self, unregister=False):
        if not self.registered:
            return
        
        self.__class__._to_unregister.add(self)
        
        if unregister:
            self.__class__._unregister_from_graph()
            
    def request_registration(self, instance_id):
        if instance_id is None:
            assert self.allow_random_key, "No key specified"
            instance_id = self.__class__.get_random_id()
            
        self.instance_id = instance_id
        self.__class__._to_register.add(self) 
        
    def on_registered(self):
        pass

    def on_unregistered(self):
        pass
    
    @property
    def registered(self):
        return self._instances.get(self.instance_id) is self
    
    def __bool__(self):
        return self.registered
    
    def __str__(self):
        return "(RegisteredInstance {}: {})".format(self.__class__.__name__, self.instance_id)
        
class InstanceRegister(TypeRegister):
    
    def __new__(meta, name, parents, attrs):       
        
        parents += (InstanceMixins,) 
        cls = super().__new__(meta, name, parents, attrs)
        
        if not hasattr(cls, "_instances"):
            cls._instances = {}
            cls._subscribers = set()
            cls._to_register = set()
            cls._to_unregister = set()
                        
        return cls
    
    def notify_of_registration(cls, instance):
        for subscriber in cls._subscribers:
            subscriber.notify_registration(instance)
            
    def notify_of_unregistration(cls, instance):
        for subscriber in cls._subscribers:
            subscriber.notify_unregistration(instance)
    
    def subscribe(cls, subscriber, ignore_existing=False):
        cls._subscribers.add(subscriber)
        # Register existing instances
        if ignore_existing:
            return
        
        for instance in cls._instances.values():
            subscriber.notify_registration(instance)
        
    def unsubscribe(cls, subscriber):
        cls._subscribers.remove(subscriber)
    
    def get_entire_graph_ids(cls, instigator=None):
        instance_ids = (k for k, v in cls._instances.items() if v != instigator)
        register_ids = (i.instance_id for i in cls._to_register if i != instigator)
        return chain(instance_ids, register_ids)
    
    def get_graph_instances(cls, only_real=True):
        if only_real:
            return cls._instances.values()
        return chain(cls._instances.values(), cls._to_register)
    
    def graph_has_instance(cls, instance_id):
        return instance_id in cls._instances 
    
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
            
    def remove_from_entire_graph(cls, instance_id):
        if instance_id in cls._instances:
            instance = cls._instances.pop(instance_id)
            instance.on_unregistered()
            cls.notify_of_unregistration(instance)
            return instance
                
        for i in cls._to_register:
            if i.instance_id != instance_id:
                continue
            
            cls._to_register.remove(i)
            return i
    
    def get_random_id(cls):
        all_instances = list(cls.get_entire_graph_ids())
        
        for key in range(len(all_instances) + 1):
            if not key in all_instances:
                return key
    
    def update_graph(cls):
        if cls._to_register:
            for instance in cls._to_register.copy():
                cls._register_to_graph(instance)
        
        if cls._to_unregister:   
            for instance in cls._to_unregister.copy():
                cls._unregister_from_graph(instance)
                
    def _register_to_graph(cls, instance):
        cls._instances[instance.instance_id] = instance
        cls._to_register.remove(instance)
        
        try:
            instance.on_registered()
            
        except Exception as err:
            raise err
        
        finally:
            cls.notify_of_registration(instance)
        
    def _unregister_from_graph(cls, instance):
        cls._instances.pop(instance.instance_id)
        cls._to_unregister.remove(instance)
        
        try:
            instance.on_unregistered()
            
        except Exception as err:
            raise err
        
        finally:
            cls.notify_of_unregistration(instance)
        
    def __iter__(cls):
        return iter(cls._instances.values()) 
    
class ReplicableRegister(InstanceRegister):
    
    def __new__(meta, cls_name, bases, attrs):
        # If this isn't the base class
        if bases:
            # Get all the member methods
            for name, value in attrs.items():
                # Check it's not in parents (will have been checked)
                if meta.found_in_parents(name, bases):
                    continue
                
                # Wrap them with permission
                if isinstance(value, (FunctionType, classmethod, staticmethod)):
                    # Recreate RPC from its function
                    if isinstance(value, RPC):
                        print("Found pre-wrapped RPC call: {}, re-wrapping... (any data defined in __init__ will be lost)".format(name))
                        value = value._func
                        
                    value = meta.permission_wrapper(value)
                    
                    # Automatically wrap RPC
                    if meta.is_rpc(value) and not isinstance(value, RPC):
                        value = RPC(value)
                        
                    attrs[name] = value
        
        return super().__new__(meta, cls_name, bases, attrs)
    
    def is_rpc(func):
        try:
            annotations = func.__annotations__
        except AttributeError:
            if not hasattr(func, "__func__"):
                return False
            annotations = func.__func__.__annotations__
        
        try:
            return_type = annotations['return']
        except KeyError:
            return False
        
        return return_type in Netmodes
    
    def found_in_parents(name, parents):
        for parent in parents:
            if name in dir(parent):
                return True
    
    def permission_wrapper(func):
        simulated_proxy = Roles.simulated_proxy
        func_is_simulated = is_simulated(func)
        
        @wraps(func)
        def func_wrapper(*args, **kwargs):

            try:
                assumed_instance = args[0]
                
            # Static method needs no permission
            except IndexError:
                return func(*args, **kwargs)
            
            else:
                # Check that the assumed instance/class has a role method
                if hasattr(assumed_instance, "roles"):
                    arg_roles = assumed_instance.roles
                    # Check that the roles are of an instance
                    try:
                        local_role = arg_roles.local
                    except AttributeError:
                        return
                    
                    # Permission checks
                    if (local_role > simulated_proxy or(func_is_simulated and local_role >= simulated_proxy)):
                        return func(*args, **kwargs)
                    
                    elif getattr(assumed_instance, "verbose_execution", False):
                        print("Error executing '{}': Function does not have permission:\n{}".format(func.__qualname__, arg_roles))
                        
                elif getattr(assumed_instance, "verbose_execution", False):
                    print("Error executing {}: Function does not have permission roles")
        
        return func_wrapper
    
