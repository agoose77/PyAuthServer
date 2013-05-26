'''
Created on 10 Apr 2013

@author: Angus
'''

# Game classes               
from bge import types, logic, events
from mathutils import Vector

from time import time
from collections import deque

from enums import Physics, Animations, ParentStates
from attributes import PhysicsData, AnimationData
from network import Controller, Replicable, Attribute, simulated, Roles, StaticValue, Netmodes, RPC, reliable, WorldInfo

import random

class InputStatus:
    def __init__(self, event):
        self.event = event
    
    @property
    def status(self):
        return logic.keyboard.events[self.event]
    
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
    def none(self):
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
                status = cache[name] = InputStatus(event)
                return status
            
            return super().__getattribute__(name)

class PlayerInputs(InputManager):
    mappings = {"chat": events.CKEY, "jump": events.JKEY}

class GameObject(types.KX_GameObject):
    '''Creates a Physics and Graphics mesh for replicables
    Fixes parenting relationships between actors which are proxies'''
    def __new__(cls, *args, **kwargs):
        cont = logic.getCurrentController()
        obj = cont.owner.scene.addObject(cls.mesh_name, cont.owner)
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
    
    def on_delete(self):
        super().on_delete()
        self.endObject()
        
    def __repr__(self):
        '''Cleaner printing of object'''
        return object.__repr__(self)

class PlayerController(Controller):
            
    input_class = PlayerInputs
    
    round_trip_time = 0.0
    ping_sample_time = 0.5
    last_sample_time = 0.0
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Add input class
        if WorldInfo.netmode != Netmodes.server:
            self.create_player_input()

        # Add time started and accumulator
        self.started = time()
        self.rtt_accumulator = deque()
    
    def create_player_input(self):
        super().create_player_input()
        
        self.chat = Chat()
         
    @RPC
    @reliable
    def set_name(self, name: StaticValue(str)) -> Netmodes.server:
        self.name = name
    
    @RPC
    @reliable
    def send_message(self, message: StaticValue(str)) -> Netmodes.server:
        for controller in WorldInfo.subclass_of(type(self)):
            controller.receive_message(self.name, message)
            
    @RPC
    @reliable
    def receive_message(self, name: StaticValue(str), message: StaticValue(str)) -> Netmodes.client:
        print("Message received from {}: {}".format(name, message))
        self.chat.display_message(name + ":" + message + ":" + str(WorldInfo.elapsed))
        
    @property
    def elapsed(self):
        '''Elapsed time since creation
        used to find RTT'''
        return time() - self.started    
    
    def update_rtt(self, rtt):
        self.rtt_accumulator.append(round_trip_time)
        
        if len(self.rtt_accumulator) > 8:
            self.rtt_accumulator.popleft()
        
        self.round_trip_time = sum(self.rtt_accumulator) / len(self.rtt_accumulator)
        
    def player_update(self, delta):
        super().player_update(delta)
        
        inputs = self.player_input
        
        if inputs.chat.pressed:
            self.send_message("Hello world") 
            
        if inputs.jump.pressed:
            self.pawn.server_play_animation("jump", 30, mode=logic.KX_ACTIONACT_PLAY) 
                 
class Actor(GameObject, Replicable):
    ''''A basic actor class 
    Inherits from GameObject to display mesh and collide'''  
      
    local_role = Roles.authority
    remote_role = Roles.simulated_proxy
    
    owner = Attribute(type_of=Replicable, notify=True)
    animation = Attribute(type_of=AnimationData, notify=True)
    physics = Attribute(PhysicsData(Physics.rigidbody), complain=False)
    
    update_simulated_position = True
    mesh_name = "Sphere"
        
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

class Chat(Actor):
    mesh_name = "Chat"
    
    local_role = Roles.authority
    remote_role = Roles.simulated_proxy
    
    physics = Attribute(PhysicsData(Physics.none), complain=False)
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.clear_messages()
    
    @property
    def message_list(self):
        return sorted(self.children, key=lambda c: c.localPosition.y)
    
    def clear_messages(self):
        for message in self.message_list:
            message['Text'] = ""
    
    def display_message(self, message_text):
        last_message = None
        
        for message in self.message_list:
            try:
                last_message['Text'] = message['Text']
            except TypeError:
                pass
            last_message = message
        
        message['Text'] = message_text 
        
    @simulated
    def update(self, delta_time):
        controller = next(WorldInfo.subclass_of(PlayerController))
        self.worldPosition = controller.pawn.worldPosition.copy()