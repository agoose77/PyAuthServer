'''
Created on 10 Apr 2013

@author: Angus
'''

# Game classes               
from bge import types, logic, events
from mathutils import Vector

from time import time
from collections import deque

from enums import Physics, Animations
from attributes import PhysicsData, AnimationData
from network import BaseController, Replicable, Attribute, simulated, Roles, StaticValue, Netmodes, RPC, reliable, WorldInfo


class GameObject(types.KX_GameObject):
    '''Creates a Physics and Graphics mesh for replicables'''
    def __new__(cls, *args, **kwargs):
        cont = logic.getCurrentController()
        scene = logic.getCurrentScene()
        obj = scene.addObject(cls.mesh_name, cont.owner)
        return super().__new__(cls, obj)

    def on_delete(self):
        super().on_delete()
        self.endObject()
        
    def __repr__(self):
        '''Cleaner printing of object'''
        return object.__repr__(self)


class PlayerController(BaseController):
            
    input_class = lambda s, o: None
    
    ping_sample_time = 0.2
    last_sample_time = 0.0
    
    rtt = 0.0
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Add input class
        if WorldInfo.netmode == Netmodes.client:
            self.create_player_input()
        
        # Add time started and accumulator
        self.started = time()
        self.rtt_accumulator = deque()
        
    @property
    def elapsed(self):
        '''Elapsed time since creation
        used to find RTT'''
        return time() - self.started    
    
    def process_inputs(self, inputs):
        result = None
        return result
    
    def update_rtt(self, rtt):
        self.rtt_accumulator.append(rtt)
        if len(self.rtt_accumulator) > 8:
            self.rtt_accumulator.popleft()
        
        self.rtt = sum(self.rtt_accumulator) / len(self.rtt_accumulator)
        
    @RPC
    def server_move(self, movement: StaticValue(float)) -> Netmodes.server:
        #output = self.process_inputs(movement.inputs)
        #if movement.output.difference(output) > 1.0: correct
        #movement = Move(movement.timestamp, output)
        self.client_adjust_move(movement, WorldInfo.elapsed)
    
    @RPC
    def client_adjust_move(self, movement: StaticValue(float), server_elapsed: StaticValue(float)) -> Netmodes.client:
        rtt = self.elapsed - movement #.timestamp
        
        # Update rtt smoothly
        self.update_rtt(rtt)
        
    def replicate_move(self, move):
        #movement = (WorldInfo.elapsed, self.inputs, move)
        movement = move
        self.saved_moves.append(movement)
        self.server_move(movement)
    
    def player_move(self):
        #perform physics updates using inputs
        #output = self.process_inputs(self.inputs)
        self.replicate_move(self.elapsed)    
    
    def player_update(self, delta):
        if logic.keyboard.active_events.get(events.AKEY):
            self.pawn.server_play_animation("jump", 30, mode=logic.KX_ACTIONACT_PLAY)
        #self.player_move()

        
class Actor(GameObject, Replicable):
    ''''A basic actor class 
    Inherits from GameObject to display mesh and collide'''  
      
    local_role = Roles.authority
    remote_role = Roles.simulated_proxy
    mesh_name = "Sphere"
    
    owner = Attribute(type_of=Replicable, notify=True)
    animation = Attribute(type_of=AnimationData, notify=True)
    physics = Attribute(PhysicsData(Physics.rigidbody), complain=False)
    
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
        yield from super().conditions(is_owner, is_complaint, is_initial)

        if is_initial:
            yield "owner"    
        
        if is_complaint:
            yield "animation"
        
        yield "physics"
