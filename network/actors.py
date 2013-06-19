from .bases import Attribute, InstanceRegister
from .enums import Roles
from .modifiers import simulated

from inspect import getmembers
from collections import defaultdict, deque

class Replicable(metaclass=InstanceRegister):
    '''Replicable base class
    Holds record of instantiated replicables and replicable types
    Default method for notification and generator for conditions.
    Additional attributes for attribute values (from descriptors) and complaining attributes'''
    _by_types = defaultdict(list)
     
    roles = Attribute(Roles(Roles.authority, Roles.none))
    
    def __init__(self, instance_id=None, register=False, static=True, **kwargs):
        # If this is a locally authoritative
        self._local_authority = False
        
        # Instantiate parent
        super().__init__(instance_id=instance_id, register=register, allow_random_key=True)
        
        self._calls = deque()
        self._data = {}
        self._complain = {}    
        self._subscribers = []  
        self._rpc_functions = []
        
        # Ensures all RPC / attributes registered for use
        for name, value in sorted(getmembers(self)):
            getattr(self, name)
        
        # If this is a static mapping  
        self._static = static and instance_id is not None
        
        # Creation callback
        self.on_create()
    
    def on_create(self):
        pass
    
    @classmethod
    def _create_or_return(cls, base_cls, instance_id, register=False):
        '''Called by the replication system'''
        # Try and match an existing instance
        try:
            existing = cls.get_from_graph(instance_id)
        
        # If we don't find one, make one
        except LookupError:
            return base_cls(instance_id=instance_id, register=register, static=False)
        
        else:
            # If we find a locally defined replicable (if instance_id was None when created -> not static)
            if existing._local_authority: # Without authority
                # Make the class and overwrite the id
                return base_cls(instance_id=instance_id, register=register, static=False)
            
            return existing
    
    def request_registration(self, instance_id, verbose=False):
        # This is static or replicated then it's local
        if instance_id is None: 
            self._local_authority = True
            
        # Therefore we will have authority to change things
        if instance_id in self.get_entire_graph_ids():
            instance = self.remove_from_entire_graph(instance_id)
            
            # If the instance is not local, then we have a conflict
            assert instance._local_authority, "Authority over instance id {} is unresolveable".format(instance_id)
            
            # Possess the instance id
            super().request_registration(instance_id)
            
            if verbose:
                print("Transferring authority of id {} from {} to {}".format(instance_id, instance, self))
            
            # Forces reassignment of instance id
            instance.request_registration(None)
        
        if verbose:
            print("Create {} with id {}".format(self.__class__.__name__, instance_id))
            
        # Possess the instance id
        super().request_registration(instance_id)
          
    def possessed_by(self, other):
        self.owner = other
    
    def unpossessed(self):
        self.owner = None
    
    def subscribe(self, subscriber):
        self._subscribers.append(subscriber)
    
    def unsubscribe(self, subscriber):
        self._subscribers.remove(subscriber)
        
    def on_registered(self):
        self.__class__._by_types[type(self)].append(self)
        super().on_registered()
        
    def on_unregistered(self):
        super().on_unregistered()
        self.__class__._by_types[type(self)].remove(self) 
        for subscriber in self._subscribers:
            subscriber(self)
    
    def on_notify(self, name):
        print("{} attribute of {} was changed by the network".format(name, self.__class__.__name__))
        
    def conditions(self, is_owner, is_complaint, is_initial):
        if is_complaint or is_initial:
            yield "roles"
        
    def update(self, elapsed):
        pass
    
    def __description__(self):
        return hash(self.instance_id)
    
class BaseWorldInfo(Replicable):
    '''Holds info about game'''
    netmode = None
    rules = None
    
    roles = Attribute(Roles(Roles.authority, Roles.simulated_proxy))    
    elapsed = Attribute(0.0, complain=False)
    
    @property
    def actors(self):
        return Replicable.get_graph_instances()
    
    def subclass_of(self, actor_type):
        return (a for a in self.actors if isinstance(a, actor_type))
    
    def conditions(self, is_owner, is_complain, is_initial):
        if is_initial:
            yield "elapsed"

    @simulated
    def update(self, delta):
        self.elapsed += delta
    
    type_is = Replicable._by_types.get
    get_actor = Replicable.get_from_graph
                
class Controller(Replicable):
    
    roles = Attribute(Roles(Roles.authority, Roles.autonomous_proxy))    
    pawn = Attribute(type_of=Replicable, complain=True)
    
    input_class = None
    
    def possess(self, replicable):
        self.pawn = replicable
        self.pawn.possessed_by(self)
    
    def unpossess(self):
        self.pawn.unpossessed()
        self.pawn = None
    
    def on_unregistered(self):
        super().on_unregistered()  
        self.pawn.request_unregistration()
                
    def conditions(self, is_owner, is_complaint, is_initial):
        if is_complaint:
            yield "pawn"  
        
    def create_player_input(self):
        if callable(self.input_class):
            self.player_input = self.input_class()
            
    def player_update(self, elapsed):
        pass