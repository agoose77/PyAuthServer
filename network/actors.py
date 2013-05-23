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
    _by_types = defaultdict(list)
    _subscribers = []
    _instances = {}
    _types = {}
    
    def __init__(self, network_id=None):
        # Create a flag that is set when attributes change (if permitted)
        self._data = {}
        self._calls = deque()
        self._complain = {}

        # Invoke descriptors to register values
        for name, value in getmembers(self):
            getattr(self, name)
        
        # Store id of replicable
        if network_id is None:
            network_id = choice([i for i in range(len(self._instances) + 1) if not i in self._instances])
        
        # Enable access by network id or type
        self._instances[network_id] = self
        self._by_types[type(self)].append(self)
        
        self.network_id = network_id
    
    def possessed_by(self, other):
        self.owner = other
    
    def unpossessed(self):
        self.owner = None
    
    def subscribe(self, subscriber):
        self._subscribers.append(subscriber)
    
    def unsubscribe(self, subscriber):
        self._subscribers.remove(subscriber)
        
    def on_delete(self):
        self._instances.pop(self.network_id)
        self._by_types[type(self)].remove(self)
        
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
    
    def typed_actors(self, actor_type):
        '''Returns all actors in scene
        @param actor_type: type filter (class)'''
        return Replicable._by_types[actor_type]
    
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
                
class BaseController(Replicable):
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
        print("UPD")
        pass
    
    def update(self, delta):
        pass