'''
Created on 10 Apr 2013

@author: Angus
'''

# Game classes               
from bge import types, logic, events, constraints
from mathutils import Vector, Matrix, Euler
from aud import Factory, Device, device as get_audio_device

from collections import deque
from functools import partial
from operator import lt as less_than_operator
from math import radians
from itertools import chain

from .enums import Physics, Animations, ParentStates, PhysicsTargets
from .data_types import PhysicsData, AnimationData, InputManager
from .states import MoveManager, RenderState, PlayerMove
from .tools import AttatchmentSocket

from random import randint
from functools import partial
from network import Controller, Replicable, Attribute, Roles, StaticValue, Netmodes, RPC, reliable, WorldInfo, simulated, NetmodeOnly

def save(replicable):
    replicable.render_state.save()

def switch(obj, replicable):
    if (replicable in obj.childrenRecursive or replicable == obj):
       replicable.render_state.save()
    else:
        replicable.render_state.restore()

def update_physics_for(obj, deltatime):
    ''' Calls a physics simulation for deltatime
    Rewinds other actors so that the individual is the only one that is changed by the end'''
   
    # Get all children
    all_children = obj.childrenRecursive
    
    for replicable in WorldInfo.subclass_of(Actor):
        # Start at the parents and traverse
        if not replicable.parent:
            replicable.physics_to_world(callback=save, deltatime=deltatime)
    # Tick physics
    obj.scene.updatePhysics(deltatime)

    switch_cb = partial(switch, obj)
    # Restore objects that aren't affiliated with obj
    for replicable in WorldInfo.subclass_of(Actor):
        if not replicable.parent:
            # Apply results
            replicable.world_to_physics(callback=switch_cb, deltatime=deltatime)
           
             
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
                self.owner = other
        else:  
            super().setParent(other)
            self.owner = other

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
    
    def on_create(self):
        super().on_create()
        
        # RTT data        
        self.round_trip_time = 0.0
        self.ping_sample_time = 0.5
        self.last_sample_time = 0.0
        
        # Move data    
        self.moves = MoveManager()
        self.correction = None    
        
        self.previous_time = None
        self.last_sent = None
        
        self.delta_threshold = 0.8
        self.considered_error = 0.1
        
        self.valid_inputs = 0
        self.invalid_inputs = 0
        
        self.invalid = False
        
        # Add input class
        if WorldInfo.netmode != Netmodes.server:
            self.create_player_input()
        
        # Add time started and accumulator
        self.rtt_accumulator = deque()
        
        # Setup player info
        self.create_info()
    
    @NetmodeOnly(Netmodes.server)
    def create_info(self):
        self.info = ControllerInfo()
    
    @RPC
    def client_hear_sound(self, path:StaticValue(str), position:StaticValue(Vector))->Netmodes.client:
        device = get_audio_device()
        device.listener_location = position
        sound = Factory(logic.expandPath(path))
        handle = device.play(sound)   
        
    def calculate_move(self, move):
        """Returns velocity and angular velocity of movement
        @param move: move to execute"""
        return Vector(), Vector()
    
    def check_delta_time(self, timestamp, deltatime):
        '''A boolean check that the deltatime we're sent is close to the calculated one
        There will be "differences" so this is crude'''
        current_time = WorldInfo.elapsed
        
        try:
            rough_deltatime = current_time - self.previous_time
        except TypeError:
            return True
        
        else:
            try:
                error_fraction = (rough_deltatime / deltatime)
            except ZeroDivisionError:
                pass
            
            else:
                allowed = (1 + self.delta_threshold) > error_fraction > (1 - self.delta_threshold)
                
                if allowed:
                    self.valid_inputs += 1
                else:
                    self.invalid_inputs += 1
                    
                try:
                    if (self.invalid_inputs / self.valid_inputs):
                        self.invalid = True
                except ZeroDivisionError:
                    pass
            
        finally:
            self.previous_time = current_time
            
        return True
    
    @RPC
    def server_perform_move(self, move_id: StaticValue(int, max_value=65535), timestamp: StaticValue(float), deltatime: StaticValue(float), inputs: StaticValue(InputManager), physics: StaticValue(PhysicsData)) -> Netmodes.server:
        allowed = self.check_delta_time(timestamp, deltatime)
        
        if not allowed:
            print("Move delta time invalid")
            return
        
        # Get current pawn object that we control
        pawn = self.pawn

        # Create a move to simulate
        move = PlayerMove(timestamp, deltatime, inputs)
        # Determine the velocity and rotation outputs
        pawn.physics.velocity, pawn.physics.angular = self.calculate_move(move)
        
        # Simulate
        update_physics_for(pawn, deltatime)
        
        # Stop bullet simulating this in the normal tick
        pawn.stop_moving()
                
        # Error between server and client
        position_difference = (pawn.physics.position - physics.position).length
        rotation_difference = abs(pawn.physics.orientation.z - physics.orientation.z)
                
        # Margin of error allowed between the two
        position_margin = 0.2
        rotation_margin = radians(3)

        # Check the error between server and client
        if position_difference > position_margin or rotation_difference > rotation_margin or inputs.resimulate.pressed:
            self.client_correct_move(move_id, pawn.physics)
        
        else:
            self.client_acknowledge_move(move_id)
    
    @RPC
    def client_acknowledge_move(self, move_id:StaticValue(int, max_value=65535)) -> Netmodes.client:
        self.moves.remove_move(move_id)
    
    @RPC
    def client_correct_move(self, move_id: StaticValue(int, max_value=65535), physics: StaticValue(PhysicsData)) -> Netmodes.client:
        self.correction = move_id, physics
        self.pawn.physics = physics
        # Stop Bullet running old velocity
        # We're only trying to set non-deltatime modified values (pos, ori)
        self.pawn.stop_moving(PhysicsTargets.network)
        
    def post_physics(self, delta_time):
        moves = self.moves
        pawn = self.pawn
        
        if not pawn.registered:
            return

        # Ensures that any parent relationships are updated
        # Ensures friction reduces velocity

        # If we have no moves we can't re-simulate or send latest move
        if not moves:
            return

        # If we have no correction then the latest move is set
        if not self.correction:
            # Get the move ID
            move_id = moves.latest_move
            
            # If we've not sent it before
            if move_id != self.last_sent:
                
                # Get the latest move
                latest_move = moves.get_move(move_id)
                # Send move
                self.server_perform_move(move_id, *chain(latest_move, (pawn.physics, )))
                self.last_sent = move_id
        
        # Otherwise we need to simulate the move
        else:
            # Get ID of correction
            correction_id = self.correction[0]
            # Find the successive moves
            following_moves = list(self.moves.sorted_moves(partial(less_than_operator, correction_id)))
            # Inform console we're resimulating
            print("Resimulating from {}".format(correction_id), len(following_moves))
            
            # Re run all moves
            for replay_id, replay_move in following_moves:
                # Get resimlation of move
                pawn.physics.velocity, pawn.physics.angular = self.calculate_move(replay_move)
                # Update bullet
                update_physics_for(pawn, replay_move.deltatime)
            
            # We didn't send the last one as it needed simulating
            if replay_id != self.last_sent:
                # Tell server about move
                self.server_perform_move(replay_id, *chain(replay_move, (pawn.physics,)))
                self.last_sent = replay_id
                
            # Remove the corrected move (no longer needed)
            self.moves.remove_move(correction_id)
            # Empty correction to prevent recorrecting
            self.correction = None
    
    def update_rtt(self, round_trip_time):
        self.rtt_accumulator.append(round_trip_time)
        
        if len(self.rtt_accumulator) > 8:
            self.rtt_accumulator.popleft()
        
        self.round_trip_time = sum(self.rtt_accumulator) / len(self.rtt_accumulator)
    
    def player_update(self, delta_time):
        # Make sure we have a pawn object
        pawn = self.pawn
        
        if not pawn.registered:
            return
        
        timestamp = WorldInfo.elapsed
        
        # Create move object (as sent end of tick, playerinput is ok to be muteable)
        move = PlayerMove(timestamp=timestamp, deltatime=delta_time, inputs=self.player_input.static)
        
        # If no correction, make use of simulation
        # Otherwise it would be invalid anyway
        if self.correction is None:
            velocity, angular = self.calculate_move(move)
            # Set angular velocity and velocity (keep Z velocity)
            pawn.physics.velocity[:-1] = velocity[:-1]
            pawn.physics.angular = angular
            
        # Store move regardless
        self.moves.add_move(move)   

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
    
    def on_registered(self):
        super().on_registered()

        try:
            creation_rule = WorldInfo.rules.on_create_actor
        except AttributeError:
            pass
        else:
            creation_rule(self)
        
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
            except:
                pass
    
    def stop_moving(self, target=None):
        if target is None:
            network = blender = True
        elif target == PhysicsTargets.network:
            network, blender = True, False
        elif target == PhysicsTargets.blender:
            network, blender = False, True
            
        physics = self.physics
        
        if blender:
            if physics.mode == Physics.rigidbody:
                self.worldLinearVelocity.zero()
                self.worldAngularVelocity.zero()
            elif physics.mode == Physics.character:
                constraints.getCharacter(self).walkDirection = Vector()
        if network:
            physics.velocity.zero()
            physics.angular.zero()

    def physics_to_world(self, condition=None, callback=None, deltatime=1.0):
        physics = self.physics
        
        if callable(condition):
            if not condition(self):
                return
        
        if self.children:
            for child in self.children:
                child.physics_to_world(condition=condition, callback=callback)
                
        if physics.mode == Physics.rigidbody:
            self.worldLinearVelocity = physics.velocity
            
        elif physics.mode == Physics.character:
            constraints.getCharacter(self).walkDirection = physics.velocity * deltatime
            physics.simulate_dynamics(deltatime)
        
        self.worldPosition = physics.position 
        self.worldOrientation = physics.orientation
        
        if callable(callback):
            callback(self)
            
    def world_to_physics(self, condition=None, callback=None, deltatime=1.0):
        physics = self.physics
        deltatime = max(deltatime, 1/60)
        if callable(condition):
            if not condition(self):
                return
        
        if self.children:
            for child in self.children:
                child.world_to_physics(condition=condition, callback=callback)
        
        physics.position = self.worldPosition.copy()
        physics.orientation = self.worldOrientation.to_euler()

        if physics.mode == Physics.rigidbody:
            physics.velocity = self.worldLinearVelocity.copy()
            
        elif physics.mode == Physics.character:
            physics.velocity = constraints.getCharacter(self).walkDirection / deltatime
        
        if callable(callback):
            callback(self)
    
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
    
    def align_from(self, other):
        direction = Vector((1, 0, 0)); direction.rotate(other.physics.orientation)
        orientation = Vector((1, 0, 0)).rotation_difference(direction)
        self.physics.orientation = orientation.to_euler()
        
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
        
        is_simulated = (self.roles.remote == Roles.simulated_proxy) or (not is_owner and self.roles.remote == Roles.autonomous_proxy)
        if is_simulated and self.update_simulated_position:
            yield "physics"
