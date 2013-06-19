'''
Created on 10 Apr 2013

@author: Angus
'''

# Game classes               
from bge import types, logic, events, constraints
from mathutils import Vector, Matrix

from time import monotonic
from collections import deque

from .enums import Physics, Animations, ParentStates
from .data_types import PhysicsData, AnimationData

from network import Controller, Replicable, Attribute, Roles, StaticValue, Netmodes, RPC, reliable, WorldInfo, simulated
    
class RenderState:
    def __init__(self, obj):
        self.obj = obj
        self.ignore = False
        self.save()
        
    def save(self):
        self.transform = self.obj.worldTransform.copy()
        self.velocity = self.obj.worldLinearVelocity.copy()
        self.angular = self.obj.worldAngularVelocity.copy()
    
    def restore(self):
        self.obj.worldTransform = self.transform 
        self.obj.worldLinearVelocity = self.velocity
        self.obj.worldAngularVelocity = self.angular 
     
    def __enter__(self):
        self.ignore = False
        self.save()
        
    def __exit__(self, *a, **k):
        if not self.ignore:
            self.restore()

class GameObject(types.KX_GameObject):
    '''Creates a Physics and Graphics mesh for replicables
    Fixes parenting relationships between actors which are proxies'''
    def __new__(cls, *args, **kwargs):
        existing = kwargs.get("object")
        
        if not existing:
            transform = Matrix.Translation(cls.physics.value.position) * cls.physics.value.orientation.to_matrix().to_4x4() * Matrix.Scale(1, 4)
            obj = logic.getCurrentScene().addObject(cls.obj_name, transform, 0)
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
    
    def __repr__(self):
        '''Cleaner printing of object'''
        return object.__repr__(self)

class ControllerInfo(Replicable):
    roles = Attribute(Roles(Roles.authority, Roles.simulated_proxy))    
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
    
    def on_create(self):
        super().on_create()
        
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
    
    def update_rtt(self, round_trip_time):
        self.rtt_accumulator.append(round_trip_time)
        
        if len(self.rtt_accumulator) > 8:
            self.rtt_accumulator.popleft()
        
        self.round_trip_time = sum(self.rtt_accumulator) / len(self.rtt_accumulator)
        
class Actor(GameObject, Replicable):
    ''''A basic actor class 
    Inherits from GameObject to display mesh and collide'''  
      
    roles = Attribute(Roles(Roles.authority, Roles.simulated_proxy))    
    owner = Attribute(type_of=Replicable, notify=True)
    animation = Attribute(type_of=AnimationData, notify=True)
    physics = Attribute(PhysicsData(Physics.rigidbody), complain=False)
    
    update_simulated_position = True
    obj_name = "Sphere"
    
    def on_create(self):
        self.render_state = RenderState(self)
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
    
    def on_transition(self, previous, current):
        pass
    
    def is_state(self, obj):
        for base in self.allowed_transitions:
            if isinstance(obj, base):
                return True
    
    def on_new_collision(self, collider):
        if self.is_state(collider):
            self.transition(collider)
    
    def on_end_collision(self, collider):
        if self.is_state(collider):
            try:
                self.remove_state(collider)
            except:pass
    
    def physics_to_world(self):
        physics = self.physics
        
        self.worldPosition = physics.position
        self.worldOrientation = physics.orientation
        
        if physics.mode == Physics.rigidbody:
            self.worldLinearVelocity = physics.velocity
        else:
            constraints.getCharacter(self).walkDirection = physics.velocity / logic.getLogicTicRate()
    
    def world_to_physics(self):
        physics = self.physics
        
        physics.position = self.worldPosition
        physics.orientation = self.worldOrientation.to_euler()
        
        if physics.mode == Physics.rigidbody:
            physics.velocity = self.worldLinearVelocity
        else:
            physics.velocity = constraints.getCharacter(self).walkDirection * logic.getLogicTicRate()
    
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
    
    def local_space(self, velocity):
        velocity = velocity.copy()
        rotation = self.physics.orientation.copy()
        rotation.x = rotation.y = 0
        velocity.rotate(rotation)
        return velocity
             
    def on_notify(self, name):
        '''Called when network variable is changed
        @param name: name of attribute'''
        if name == "animation":
            self.play_animation(self.animation)
        else:
            super().on_notify(name) 
    
    def conditions(self, is_owner, is_complaint, is_initial):
        '''Generator dictates which attributes must be replicated'''
        yield from super().conditions(is_owner, is_complaint, is_initial)
        
        if is_initial:
            yield "physics"
            yield "owner" 
        
        if is_complaint and 0:
            yield "animation"
        
        if self.roles.remote == self.roles.simulated_proxy and self.update_simulated_position:
            yield "physics"
