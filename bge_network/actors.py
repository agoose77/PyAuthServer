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

from time import monotonic

from .enums import Physics, Animations, ParentStates, PhysicsTargets
from .data_types import PhysicsData, AnimationData, InputManager
from .states import MoveManager, RenderState, PlayerMove
from .tools import AttatchmentSocket

from random import randint
from functools import partial
from network import Controller, Replicable, Attribute, Roles, StaticValue, Netmodes, RPC, reliable, WorldInfo, simulated, NetmodeOnly

def save(replicable, deltatime):
    replicable.render_state.save()

def switch(obj, replicable, deltatime):
    if (replicable in obj.childrenRecursive or replicable == obj):
        replicable.render_state.save()
    else:
        replicable.render_state.restore()

def update_physics_for(obj, deltatime):
    ''' Calls a physics simulation for deltatime
    Rewinds other actors so that the individual is the only one that is changed by the end'''
   
    # Get all children    
    for replicable in WorldInfo.subclass_of(Actor):
        # Start at the parents and traverse
        if not replicable.parent:
            replicable.physics_to_world(post_callback=save, deltatime=deltatime)
            
    # Tick physics
    obj.scene.updatePhysics(deltatime)
    # Create a callback with the obj argument
    switch_cb = partial(switch, obj)
    
    # Restore objects that aren't affiliated with obj
    for replicable in WorldInfo.subclass_of(Actor):
        if not replicable.parent:
            # Apply results
            replicable.world_to_physics(post_callback=switch_cb, deltatime=deltatime)
                       
class GameObject(types.KX_GameObject):
    '''Creates a Physics and Graphics mesh for replicables
    Fixes parenting relationships between actors which are proxies'''
    def __new__(cls, *args, **kwargs):
        existing = kwargs.get("object")
        
        if not existing:
            transform = Matrix.Translation(cls.physics.value.position) * cls.physics.value.orientation.to_matrix().to_4x4() * Matrix.Scale(1, 4)
            obj = logic.getCurrentScene().addObject(cls.object_name, transform, 0)
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
            
class PlayerController(Controller):
            
    input_class = lambda *a: None
    
    def on_registered(self):
        super().on_registered()
        
        # RTT used for connection info
        self.round_trip_time = 0.0
        
        # Move data    
        self.moves = MoveManager()
        
        self.previous_checked_timestamp = None
        self.last_sent_move_id = None
        
        self.correction_id = 0
        self.correction = None
        
        self.delta_threshold = 0.8
        self.considered_error = 0.1
        
        self.position_margin = 0.4
        self.rotation_margin = radians(3)
        
        self.valid_inputs = 0
        self.invalid_inputs = 0
        
        # Add input class
        if WorldInfo.netmode != Netmodes.server:
            self.create_player_input()
        
        # Add time started and accumulator
        self.rtt_accumulator = deque()
    
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
            rough_deltatime = current_time - self.previous_checked_timestamp
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
                        pass#self.invalid = True
                except ZeroDivisionError:
                    pass
            
        finally:
            self.previous_checked_timestamp = current_time
            
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
        pawn.start_simulation()
        
        # Simulate
        update_physics_for(pawn, deltatime)
        
        # Stop bullet simulating this in the normal tick
        pawn.clear_dynamics(target=PhysicsTargets.blender)
        pawn.stop_simulation()
                
        # Error between server and client
        position_difference = (pawn.physics.position - physics.position).length
        rotation_difference = abs(pawn.physics.orientation.z - physics.orientation.z)
        
        # Conditions for correction
        error_exists = position_difference > self.position_margin or rotation_difference > self.rotation_margin
        error_is_outdated = move_id < self.correction_id
        
        # Check the error between server and client
        if (error_exists and not error_is_outdated) or self.correction:
            self.client_correct_move(move_id, pawn.physics)
            
            self.correction_id = move_id
            self.correction = False
        
        # Otherwise permit the move
        else:
            self.client_acknowledge_good_move(move_id)
    
    @RPC
    def client_acknowledge_good_move(self, move_id:StaticValue(int, max_value=65535)) -> Netmodes.client:
        move = self.moves.remove_move(move_id)
        self.update_rtt(WorldInfo.elapsed - move.timestamp)
    
    @RPC
    def server_correct(self) -> Netmodes.server:
        self.correction = True
    
    @RPC
    def client_correct_move(self, move_id: StaticValue(int, max_value=65535), physics: StaticValue(PhysicsData)) -> Netmodes.client:
        self.correction = physics
        self.correction_id = move_id
        
    def post_physics(self, delta_time):
        moves = self.moves
        pawn = self.pawn
        
        if not pawn:
            return

        # If we have no moves we can't re-simulate or send latest move
        if not moves:
            return
        
        latest_id = moves.latest_move
        latest_move = moves.get_move(latest_id)
        correction = self.correction
        
        # If we have been corrected
        if correction is not None:
            correction_id = self.correction_id
            
            # Find the successive moves
            following_moves = list(self.moves.sorted_moves(partial(less_than_operator, correction_id)))
            
            # Inform console we're resimulating
            print("Resimulating from {} for {} moves".format(correction_id, len(following_moves)))
            print("Are you sure this Controller's pawn is not simulated?\n")
            
            # Set corrected position and orientation
            pawn.physics.position = correction.position
            pawn.physics.orientation = correction.orientation
            
            # Re run all moves
            for replay_id, replay_move in following_moves:
                # Get resimlation of move
                pawn.physics.velocity, pawn.physics.angular = self.calculate_move(replay_move)
                # Update bullet
                update_physics_for(pawn, replay_move.deltatime)
        
        # Otherwise just run simulation
        else:
            pawn.physics.velocity, pawn.physics.angular = self.calculate_move(latest_move)
            # Ensure that it is simulating
            pawn.start_simulation()
            update_physics_for(pawn, latest_move.deltatime)
            
            pawn.clear_dynamics(target=PhysicsTargets.blender)
            pawn.stop_simulation()
                    
        # We didn't send the last one as it needed simulating
        if latest_id != self.last_sent_move_id:
            # Tell server about move
            self.server_perform_move(latest_id, *chain(latest_move, (pawn.physics,)))
            self.last_sent_move_id = latest_id
            
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
        if not pawn:
            return
        
        timestamp = WorldInfo.elapsed
        
        # Create move object (as sent end of tick, playerinput is ok to be muteable)
        move = PlayerMove(timestamp=timestamp, deltatime=delta_time, inputs=self.player_input.static)

        # Store move regardless
        self.moves.add_move(move)   

class Actor(GameObject, Replicable):
    ''''A basic actor class 
    Inherits from GameObject to display mesh and collide'''  
      
    roles = Attribute(
                      Roles(Roles.authority, 
                            Roles.simulated_proxy)
                      )
        
    owner = Attribute(
                      type_of=Replicable, 
                      notify=True
                      )
    
    animation = Attribute(
                          type_of=AnimationData, 
                          notify=True
                          )
    
    physics = Attribute(
                        PhysicsData(Physics.rigidbody), 
                        notify=True,
                        complain=False
                        )
    
    update_simulated_position = True
    
    object_name = "Sphere"
        
    def on_registered(self):
        super().on_registered()
        
        self.render_state = RenderState(self)
        self.allowed_transitions = []
        self.states = []
        
        # Tell the physics system we need updating
        # This would be nicer as a class-registered callback        
        WorldInfo.game.physics.register_actor(self)
    
    @property
    def character_controller(self):
        return constraints.getCharacter(self)

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
    
    @simulated
    def on_new_collision(self, collider):
        if self.is_state(collider):
            self.transition(collider)
    
    @simulated
    def on_end_collision(self, collider):
        if self.is_state(collider):
            try:
                self.remove_state(collider)
            except:
                pass
    
    @simulated
    def stop_simulation(self):
        self.physics.process_dynamics = False
    
    @simulated
    def start_simulation(self):
        self.physics.process_dynamics = True
    
    @simulated
    def clear_dynamics(self, target=None):
        ''' Stop physics velocity and angular
        @param target: target to stop moving (network or local)'''
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
                self.character_controller.walkVelocity = Vector()
                self.character_controller.verticalVelocity = 0.0
                
        if network:
            # Allow pawn dynamic calculation
            physics.velocity.zero()
            physics.angular.zero()
    
    @simulated
    def physics_to_world(self, condition=None, pre_callback=None, post_callback=None, deltatime=1.0):
        '''Applies physics settings to Blender world
        @param condition: condition that determines if this child object is relevant to physics
        @param callback: callback after update
        @param deltatime: time since last physics update. Used for character physics'''

        
        if self.children:
            for child in self.children:
                child.physics_to_world(condition=condition, post_callback=post_callback, pre_callback=pre_callback, deltatime=deltatime)
        
        if callable(condition):
            if not condition(self):
                return
            
        if callable(pre_callback):
            pre_callback(self, deltatime)
        
        physics = self.physics  
        
        velocity = physics.velocity
                
        if physics.process_dynamics:
            
            if physics.mode == Physics.rigidbody:
                self.worldLinearVelocity = physics.velocity
                
            elif physics.mode == Physics.character:
                self.character_controller.walkVelocity = physics.velocity
                physics.simulate_dynamics(deltatime)
        
        self.worldPosition = physics.position 
        self.worldOrientation = physics.orientation
        
        if callable(post_callback):
            post_callback(self, deltatime)
    
    @simulated
    def world_to_physics(self, condition=None, pre_callback=None, post_callback=None, deltatime=1.0):
        '''Applies blender physics results to physics
        @param condition: condition that determines if this child object is relevant to physics
        @param callback: callback after update
        @param deltatime: time since last physics update. Used for character physics'''

        deltatime = max(deltatime, 1/60)
        
        if self.children:
            for child in self.children:
                child.world_to_physics(condition=condition, post_callback=post_callback, pre_callback=pre_callback, deltatime=deltatime)
                
        if callable(condition):
            if not condition(self):
                return
            
        if callable(pre_callback):
            pre_callback(self, deltatime)
            
        physics = self.physics 
        
        physics.position = self.worldPosition.copy()
        physics.orientation = self.worldOrientation.to_quaternion()
        
        if physics.process_dynamics:
            if physics.mode == Physics.rigidbody:
                physics.velocity = self.worldLinearVelocity.copy()
                
            elif physics.mode == Physics.character:
                physics.velocity = self.character_controller.walkVelocity.copy()
        
        if callable(post_callback):
            post_callback(self, deltatime)
    
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
    
    @simulated
    def local_to_global(self, velocity):
        velocity = velocity.copy()
        rotation = self.physics.orientation
        rotation.x = rotation.y = 0
        velocity.rotate(rotation)
        return velocity
    
    @simulated
    def align_from(self, other):
        direction = Vector((1, 0, 0)); direction.rotate(other.physics.orientation)
        orientation = Vector((1, 0, 0)).rotation_difference(direction)
        self.physics.orientation = orientation.to_quaternion()
        
    def on_notify(self, name):
        '''Called when network variable is changed
        @param name: name of attribute'''
        if name == "animation":
            self.play_animation(self.animation)
        elif name == "physics":
            WorldInfo.game.physics.add_extrapolation(self)
        else:
            super().on_notify(name) 
    
    def conditions(self, is_owner, is_complaint, is_initial):
        '''Generator dictates which attributes must be replicated'''
        yield from super().conditions(is_owner, is_complaint, is_initial)
        
        if is_initial:
            yield "physics"
            yield "owner" 
        
        if is_complaint:
            yield "animation"
        
        is_simulated = (self.roles.remote == Roles.simulated_proxy) or (not is_owner and self.roles.remote == Roles.autonomous_proxy)
        if is_simulated and self.update_simulated_position:
            yield "physics"