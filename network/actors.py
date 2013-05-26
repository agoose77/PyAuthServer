from .bases import TypeRegister, Attribute, StaticValue
from .enums import Roles, Netmodes
from .modifiers import simulated

from random import choice
from time import time
from inspect import getmembers
from collections import defaultdict, deque

class Replicable(metaclass=TypeRegister):
    '''Replicable base class
    Holds record of instantiated replicables and replicable types
    Default method for notification and generator for conditions.
    Additional attributes for attribute values (from descriptors) and complaining attributes'''
    _types = {}
    _instances = {}
    _to_register = {}
    _to_unregister = set()
    _by_types = defaultdict(list)
    
    def __init__(self, network_id=None, register=False):
        # Create a flag that is set when attributes change (if permitted)
        self._data = {}
        self._calls = deque()
        self._complain = {}    
        self._subscribers = []  
        self._local = False  
        
        # Invoke descriptors to register values
        for name, value in getmembers(self):
            getattr(self, name)
        
        # Store id of replicable
        self._request_registration(network_id)
        
        # If we should update register immediately
        if register:
            self._update_graph()
            
    @classmethod
    def _update_graph(cls):
        for replicable in cls._to_register.values():
            replicable._register_to_graph()
            
        for replicable in cls._to_unregister:
            replicable._unregister_from_graph()
            
        cls._to_register.clear()
        cls._to_unregister.clear()
    
    @property
    def _all_actors(self):
        data = self._instances.copy(); data.update(self._to_register)
        return data
    
    @property
    def _random_id(self):
        return choice([i for i in range(len(self._all_actors) + 1) if not i in self._all_actors])
    
    @property
    def registered(self):
        return self.network_id in self._instances
    
    @classmethod
    def _create_or_return(cls, base_cls, network_id, register=False):
        all_actors = cls._instances.copy(); all_actors.update(cls._to_register)
        existing = all_actors.get(network_id)
            
        if existing is None or existing._local:
            return base_cls(network_id, register)
        
        return existing
    
    def _request_registration(self, network_id, verbose=False):
        # This is static or replicated 
        if network_id is None: 
            network_id = self._random_id
            self._local = True
            
        # Therefore we will have authority to change things
        if network_id in self._all_actors:
            storage = self._instances if network_id in self._instances else self._to_register
            
            replicable = storage.pop(network_id)
            
            assert replicable._local, "Authority over network id {} is unresolveable".format(network_id)
            
            self._to_register[network_id] = self
            
            if verbose:
                print("Transferring authority of id {} from {} to {}".format(network_id, replicable, self))
                
            replicable._request_registration(None)
        
        if verbose:
            print("Create {} with id {}".format(self.__class__.__name__, network_id))
            
        # Avoid iteration errors
        self.network_id = network_id
        self._to_register[network_id] = self
    
    def _register_to_graph(self):
        # Enable access by network id or type
        self._instances[self.network_id] = self
        self._by_types[type(self)].append(self)
        
    def _unregister_from_graph(self):
        self._instances.pop(self.network_id)
        self._by_types[type(self)].remove(self)
    
    def possessed_by(self, other):
        self.owner = other
    
    def unpossessed(self):
        self.owner = None
    
    def subscribe(self, subscriber):
        self._subscribers.append(subscriber)
    
    def unsubscribe(self, subscriber):
        self._subscribers.remove(subscriber)
        
    def on_delete(self):
        self._to_unregister.add(self)
        for subscriber in self._subscribers:
            subscriber(self)
    
    def on_notify(self, name):
        print("{} was changed by the network".format(name))
        
    def conditions(self, is_owner, is_complaint, is_initial):
        if False:
            yield
        
    def update(self, elapsed):
        pass
    
    def __description__(self):
        return hash(self.network_id)
    
class BaseWorldInfo(Replicable):
    '''Holds info about game'''
    netmode = None
    rules = None
    
    local_role = Roles.authority
    remote_role = Roles.simulated_proxy
    
    elapsed = Attribute(0.0, complain=False)
    
    @property
    def actors(self):
        return Replicable._instances.values()
    
    def type_is(self, actor_type):
        '''Returns all actors in scene
        @param actor_type: type filter (class)'''
        return Replicable._by_types[actor_type]
    
    def subclass_of(self, actor_type):
        return (a for a in Replicable._instances.values() if isinstance(a, actor_type))
    
    def get_actor(self, actor_id):
        '''Returns actor with given id
        @param actor_id: network id of actor'''
        return Replicable._instances[actor_id]
    
    def conditions(self, is_owner, is_complain, is_initial):
        if is_initial:
            yield "elapsed"

    @simulated
    def update(self, delta):
        self.elapsed += delta
                
class Controller(Replicable):
    local_role = Roles.authority
    remote_role = Roles.autonomous_proxy
    
    name = Attribute("")
    pawn = Attribute(type_of=Replicable, complain=True)
    
    input_class = None
    owner = None
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
            
        self.saved_moves = []
    
    def possess(self, replicable):
        self.pawn = replicable
        replicable.possessed_by(self)
    
    def unpossess(self):
        self.pawn.unpossessed()
        self.pawn = None
    
    def on_delete(self):
        super().on_delete()
        
        self.pawn.on_delete()
                
    def conditions(self, is_owner, is_complaint, is_initial):
        
        if is_initial:
            yield "name"
        
        if is_complaint:
            yield "pawn"  
        
    def create_player_input(self):
        if callable(self.input_class):
            self.player_input = self.input_class(self)
            
    def player_update(self, elapsed):
        pass
    
    def update(self, delta):
        pass