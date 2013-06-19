from network import keyeddefaultdict, TypeRegister
from bge import logic
from mathutils import Vector, Euler
from itertools import chain

class InputStatus:
    '''A pollable interface to an event status'''
    def __init__(self, event, interface):
        self.interface = interface
        self.event = event
    
    @property
    def status(self):
        return self.interface.events[self.event]
            
    @property
    def active(self):
        return self.pressed or self.held
    
    @property
    def pressed(self):
        return self.status == logic.KX_INPUT_JUST_ACTIVATED
    
    @property
    def held(self):
        return self.status == logic.KX_INPUT_ACTIVE
    
    @property
    def released(self):
        return self.status == logic.KX_INPUT_JUST_RELEASED
    
    @property
    def inactive(self):
        return self.status == logic.KX_INPUT_NONE

class InputManager(metaclass=TypeRegister):
    mappings = {}
    
    @classmethod
    def register_type(cls):
        cls._ordered_mappings = sorted(cls.mappings)
        cls._cache = {}
        cls._events = keyeddefaultdict(cls.new_mapping)
    
    @classmethod
    def new_mapping(cls, name):
        mappings = cls.mappings
        status = cls._cache[name] = InputStatus(mappings[name], cls._events)
        return status
    
    def __getattribute__(self, name):
        mappings = super().__getattribute__("mappings")
        
        if name in mappings:
            cache = super().__getattribute__("_cache")
            return cache[name]
        
        return super().__getattribute__(name)
    
    def update(self, events):
        self._events.update(events)
        
class AnimationData:
    __slots__ = "name", "end_frame", "timestamp", "start_frame", "mode"
    
    def __init__(self, name, end_frame, mode, start_frame=0):
        self.name = name
        self.mode = mode
        self.timestamp = 0.000 
        self.end_frame = end_frame
        self.start_frame = start_frame
    
    def __description__(self):
        return hash((self.mode, self.name, self.start_frame, self.end_frame, self.timestamp))

class PhysicsData:
    __slots__ = "mode", "timestamp", "position", "velocity", "orientation", "angular"
    
    def __init__(self, mode, position=None, velocity=None, orientation=None, angular=None):
        self.mode = mode
        self.timestamp = 0.000
        
        self.angular = Vector() if angular is None else angular
        self.position = Vector() if position is None else position
        self.velocity = Vector() if velocity is None else velocity
        self.orientation = Euler() if orientation is None else orientation
    
    @property
    def is_active(self):
        return any(self.angular) or any(self.velocity)
    
    def __description__(self):
        return hash(tuple(chain(self.position, self.velocity, self.angular, self.orientation, (self.mode,))))
    