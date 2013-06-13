'''
Created on 10 Apr 2013

@author: Angus
'''

# Game classes               
from bge import types, logic, events
from mathutils import Vector

from time import monotonic
from collections import deque

from .enums import Physics, Animations, ParentStates
from .attributes import PhysicsData, AnimationData
from network import Controller, Replicable, Attribute, simulated, Roles, StaticValue, Netmodes, RPC, reliable, WorldInfo

import random

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

class InputManager:
    mappings = {}
    _cache = {}
    
    def __init__(self, controller):
        self.controller = controller
    
    def __getattribute__(self, name):
        mappings = super().__getattribute__("mappings")
        
        if name in mappings:
            cache = super().__getattribute__("_cache")
            try:
                return cache[name]
            except KeyError:
                event = mappings[name]
                
                event_host = logic.keyboard if event in logic.keyboard.events else logic.mouse
                status = cache[name] = InputStatus(event, event_host)
                
                return status
            
            return super().__getattribute__(name)

class GameObject(types.KX_GameObject):
    '''Creates a Physics and Graphics mesh for replicables
    Fixes parenting relationships between actors which are proxies'''
    def __new__(cls, *args, **kwargs):
        existing = kwargs.get("object")
        
        if not existing:
            cont = logic.getCurrentController()
            obj = cont.owner.scene.addObject(cls.obj_name, cont.owner)
        else:
            obj = existing
        return super().__new__(cls, obj)
        
    def setParent(self, other, state=ParentStates.initial):
        if isinstance(other, GameObject):
            if state == ParentStates.initial:
                other.setParent(self, ParentStates.invoked)
            elif state == ParentStates.invoked:
                other.setParent(self, ParentStates.reply)
            elif state == ParentStates.reply:
                super().setParent(other)
        else:  
            super().setParent(other)
    
    def on_unregistered(self):        
        super().on_unregistered()
        self.endObject()
    
    def local_space(self, velocity):
        return self.worldOrientation * velocity
    
    def __repr__(self):
        '''Cleaner printing of object'''
        return object.__repr__(self)

class ControllerInfo(Replicable):
    local_role = Roles.authority
    remote_role = Roles.simulated_proxy
    
    name = Attribute("", notify=True)
    
    def on_notify(self, name):
        if name == "name":
            print("Player changed name to {}".format(self.name))
    
    def conditions(self, is_owner, is_complaint, is_initial):
        '''Generator dictates which attributes must be replicated'''

        if is_complaint:
            yield "name"
            
class PlayerController(Controller):
            
    input_class = lambda *a: None
    
    round_trip_time = 0.0
    ping_sample_time = 0.5
    last_sample_time = 0.0
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Add input class
        if WorldInfo.netmode == Netmodes.server:
            self.info = ControllerInfo()
        else:
            self.create_player_input()
        
        # Add time started and accumulator
        self.started = monotonic()
        self.rtt_accumulator = deque()
        
    @property
    def elapsed(self):
        '''Elapsed time since creation
        used to find RTT'''
        return monotonic() - self.started    
    
    def update_rtt(self, rtt):
        self.rtt_accumulator.append(round_trip_time)
        
        if len(self.rtt_accumulator) > 8:
            self.rtt_accumulator.popleft()
        
        self.round_trip_time = sum(self.rtt_accumulator) / len(self.rtt_accumulator)
        
class Actor(GameObject, Replicable):
    ''''A basic actor class 
    Inherits from GameObject to display mesh and collide'''  
      
    local_role = Roles.authority
    remote_role = Roles.simulated_proxy
    
    owner = Attribute(type_of=Replicable, notify=True)
    animation = Attribute(type_of=AnimationData, notify=True)
    physics = Attribute(PhysicsData(Physics.rigidbody), complain=False)
    
    update_simulated_position = True
    obj_name = "Sphere"
    
    def on_create(self):
        self.allowed_transitions = []
        self.states = []
        
    @property
    def current_state(self):
        try:
            return self.states[-1]
        except IndexError:
            return None
    
    def remove_state(self, obj):
        self.states.remove(obj)
        self.on_transition(obj, self.current_state)
    
    def add_state(self, obj):
        if not obj in self.states:
            current = self.current_state
            self.states.append(obj)
            self.on_transition(current, obj)
    
    def transition(self, state):
        current_state = self.current_state
        if not state in self.states:
            self.states.append(state)
        
        self.on_transition(current_state, state)
            
    def is_state(self, obj):
        for base in self.allowed_transitions:
            if isinstance(obj, base):
                return True
    
    def on_new_collision(self, collider):
        if self.is_state(collider):
            self.transition(collider)
    
    def on_end_collision(self, collider):
        if self.is_state(collider):
            self.remove_state(collider)
    
    @property
    def on_ground(self):
        return self.current_state != None
    
    def play_animation(self, animation):
        '''Plays an animation locally
        @param animation: animation object'''
        self.playAction(name=animation.name, start_frame=animation.start_frame, end_frame=animation.end_frame, play_mode=animation.mode)
        
    @RPC
    @reliable
    def server_play_animation(self, name: StaticValue(str), end:StaticValue(int), start:StaticValue(int)=0, mode:StaticValue(int)=Animations.play) -> Netmodes.server:
        '''Creates animation object
        Plays and replicates to clients'''
        # Create animation
        self.animation = AnimationData(name=name, end_frame=end, start_frame=start, mode=mode)
        self.animation.timestamp = WorldInfo.elapsed
        
        # Play on server
        self.play_animation(self.animation)
             
    def on_notify(self, name):
        '''Called when network variable is changed
        @param name: name of attribute'''
        if name == "animation":
            self.play_animation(self.animation)
        else:
            super().on_notify(name) 
    
    def conditions(self, is_owner, is_complaint, is_initial):
        '''Generator dictates which attributes must be replicated'''

        if is_initial:
            yield "owner" 
            yield "physics"   
        
        if is_complaint:
            yield "animation"
        
        if self.remote_role == Roles.simulated_proxy and self.update_simulated_position:
            yield "physics"
 