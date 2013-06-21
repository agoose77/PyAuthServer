from network import keyeddefaultdict, TypeRegister
from bge import logic
from mathutils import Vector, Euler
from itertools import chain

class InputStatus:
    '''A pollable interface to an event status'''
    def __init__(self, name, event, interface):
        self.interface = interface
        self.event = event
        self.name = name
    
    @property
    def status(self):
        return self.interface[self.event]
            
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
    
    def __repr__(self):
        status = {name: getattr(self, name) for name in dir(self.__class__) if isinstance(getattr(self.__class__, name), property)}
        console = []
        console.append("InputStatus: {}".format(self.name))
        for name, value in status.items():
            console.append("{}: {}".format(name, value))
        return '\n'.join(console) + '\n'
    
class InputManager(metaclass=TypeRegister):
    mappings = {}
    
    def __init__(self):
        self._cache = keyeddefaultdict(self.new_mapping)
        self._events = {}
    
    @classmethod
    def register_subtype(cls):
        cls._ordered_mappings = sorted(cls.mappings)
    
    @property
    def static(self):
        inst = type(self)()
        inst._events = self._events.copy()
        return inst
    
    def new_mapping(self, name):
        mappings = self.mappings
        event = mappings[name]
        status = InputStatus(name, event, self._events)
        return status
    
    def __getattribute__(self, name):
        mappings = super().__getattribute__("mappings")
        
        if name in mappings:
            cache = super().__getattribute__("_cache")
            return cache[name]
        
        return super().__getattribute__(name)
    
    def update(self, events):
        self._events.update(events)
    
    def __repr__(self):
        console = ["InputManager: {}".format(self.__class__.__name__)]
        
        for name in self.mappings:
            status = self.__getattribute__(name)
            active_status = None
            
            for attr in vars(status.__class__):
                if not isinstance(vars(status.__class__)[attr], property):
                    continue
                
                active = status.__getattribute__(attr)
                
                if active:
                    active_status = attr;break
            
           
            console.append("{}: {} ".format(name, active_status))
        
        return '\n'.join(console) + "\n"
    
class AnimationData:
    __slots__ = "name", "end_frame", "timestamp", "start_frame", "mode"
    
    def __init__(self, name, end_frame, mode, start_frame=0):
        self.name = name
        self.mode = mode
        self.end_frame = end_frame
        self.start_frame = start_frame
        self.timestamp = 0.000 
    
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
    
    def __repr__(self):
        console = ["Physics:"]
        console.append("Position: {}".format(self.position))
        console.append("Velocity: {}".format(self.velocity))
        console.append("Orientation: {}".format(self.orientation))
        return '\n'.join(console) + '\n'
    
    @property
    def is_active(self):
        return any(self.angular) or any(self.velocity)
    
    def __description__(self):
        return hash(tuple(chain(self.position, self.velocity, self.angular, self.orientation, (self.mode,))))
    