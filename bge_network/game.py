from network import Network, Replicable, WorldInfo, Roles, System

from bge import logic, events, types
import sys; sys.path.append(logic.expandPath("//../"))

from .errors import QuitGame
from .actors import Actor, PlayerController
from .enums import Physics
from .tools import quaternion_from_angular, angular_from_quaternion, CircularAverageProperty, AverageDifferenceProperty
from .data_types import PhysicsData

from time import monotonic
from functools import partial
from collections import deque

from mathutils import Vector, Euler, Quaternion
from math import copysign

class CollisionStatus:    
    """Handles collision for Actors"""
    def __init__(self, obj, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        if hasattr(types.KX_GameObject, "collisionCallbacks"):
            obj.collisionCallbacks.append(self.is_colliding)
            obj.scene.post_draw.append(self.not_colliding)
        
        self._new_colliders = set()
        self._old_colliders = set()
        self._registered = set()
    
    @property
    def colliding(self):
        return bool(self._registered)
    
    def on_start(self, other):
        pass
    
    def on_end(self, other):
        pass
    
    def is_colliding(self, other):
        # If we haven't already stored the collision
        self._new_colliders.add(other)
        
        if (not other in self._registered):
            self._registered.add(other)
            self.on_start(other)
    
    def not_colliding(self):
        # If we have a stored collision
        difference = self._old_colliders.difference(self._new_colliders)
        self._old_colliders = self._new_colliders
        self._new_colliders = set()
        
        for obj in difference:
            self._registered.remove(obj)
            self.on_end(obj)

class ExtrapolationState:
    def __init__(self, value, derivative, timestamp):
        self.value = value
        self.derivative = derivative
        self.timestamp = timestamp
        
class Extrapolator:
    
    __slots__ = "previous_state", "current_state"
    
    step = AverageDifferenceProperty(15)
    
    def __init__(self):
        self.previous_state = None
        self.current_state = None
    
    def _add_values(self, a, b):
        return a + b
    
    def _multiply_values(self, a, b):
        return a * b
    
    def _subtract_values(self, a, b):
        return a - b
    
    def _divide_values(self, a, b):
        try:
            return self._multiply_values(a, 1 / b)
        except ZeroDivisionError:
            return self._multiply_values(a, 0)
    
    def update(self, first):
        add_values = self._add_values
        multiply_values = self._multiply_values
        subtract_values = self._subtract_values
        divide_values = self._divide_values
        
        self.step = first.timestamp
        
        debug = "Position" not in self.__class__.__name__
        
        if self.previous_state is not None:
            
            second = self.previous_state
            
            current_from_first = add_values(first.value, 
                                            multiply_values(first.derivative,
                                                            self.current_state.timestamp - first.timestamp)) 
            current_from_second = add_values(second.value, 
                                            multiply_values(second.derivative,
                                                            self.current_state.timestamp - second.timestamp))   
            difference_derivative = divide_values(subtract_values(current_from_first, 
                                                                current_from_second),
                                                first.timestamp - second.timestamp)
            
            target_for_update = add_values(current_from_first, 
                                        multiply_values(difference_derivative, 
                                                        self.current_state.timestamp - first.timestamp ))
            
            target_derivative = divide_values(subtract_values(target_for_update,
                                                            self.current_state.value),
                                            self.step)
            
            self.current_state.derivative = target_derivative
            
        self.previous_state = first

class PositionExtrapolator(Extrapolator):
    pass

class OrientationExtrapolator(Extrapolator):
    
    def _add_values(self, a, b):
        c = a.copy()
        c.rotate(b)
        return c
    
    def _subtract_values(self, a, b):
        return self._add_values(a, b.inverted())

class PhysicsExtrapolator:

    time_difference = CircularAverageProperty(size=8)
    
    def __init__(self):
        self.position = PositionExtrapolator()
        self.orientation = OrientationExtrapolator()
    
    @property
    def controller(self):
        try:
            return next(WorldInfo.subclass_of(PlayerController))
        except StopIteration:
            return None
    
    @property
    def remote_time(self):
        return WorldInfo.elapsed - self.time_difference
    
    def handle_time(self, timestamp):
        '''Store the time difference so we know where to draw
        @param timestamp: timestamp of received physics'''
        try:
            current_time = timestamp + self.controller.round_trip_time / 2
        except AttributeError:
            return
            
        self.time_difference = (WorldInfo.elapsed - current_time)
        self.update_rate = timestamp
    
    def set_base(self, physics):
        timestamp = self.remote_time
        
        self.position.current_state.value = physics.position
        self.position.current_state.timestamp = timestamp
        
        self.orientation.current_state.value = physics.orientation
        self.orientation.current_state.timestamp = timestamp        
    
    def update(self, physics):
        timestamp = physics.timestamp
        
        self.handle_time(timestamp)
        
        position_state = ExtrapolationState(physics.position, physics.velocity, timestamp)
        orientation_state = ExtrapolationState(physics.orientation, quaternion_from_angular(physics.angular), timestamp)
        
        self.position.update(position_state)
        self.orientation.update(orientation_state)
        
        position_base = self.position.current_state
        orientation_base = self.orientation.current_state
        
        if position_base is None or orientation_base is None:
            self.position.current_state = ExtrapolationState(Vector(), Vector(), 0.000)
            self.orientation.current_state = ExtrapolationState(Quaternion(), Quaternion(), 0.000)
            return
        
        physics.position = position_base.value
        #physics.orientation = orientation_base.value
        
        if self.position.previous_state is None or self.orientation.previous_state is None:
            return
        
        physics.velocity = position_base.derivative
        #physics.angular = angular_from_quaternion(orientation_base.derivative)
 
class PhysicsSystem(System):
    
    def __init__(self):
        super().__init__()
        
        self.collision_listeners = {}
        self.extrapolators = {}
        self.check_for_scene_actors = True
    
    def make_actors_from_scene(self):
        '''Instantiates static actors in scene'''
        scene = logic.getCurrentScene()
        
        # Iterate over scene objects
        for obj in scene.objects:
            
            # Only find objects that haven't been converted yet
            if isinstance(obj, Replicable):
                continue
            
            # Try and access actor information or continue
            try:
                cls_name = obj['actor']
            except KeyError:
                continue
            
            # Ask for a static ID
            static_id = obj.get('static_id')
            
            # Get the class for this name
            cls = Replicable.from_type_name(cls_name)
            
            # Determine if it is a subclass of the Actor class
            if not issubclass(cls, Actor):
                continue
            
            # Find objects with physics meshes only
            no_mesh = obj.physicsType in (logic.KX_PHYSICS_NAVIGATION_MESH, 
                                        logic.KX_PHYSICS_OCCLUDER, 
                                        logic.KX_PHYSICS_NO_COLLISION)
        
            if no_mesh:
                print("Static actor  {} does not have correct physics".format(obj))
                continue
            
            # Make static actor            
            replicable = cls(object=obj, instance_id=static_id)
            replicable.world_to_physics()
            
            # Set remote role to none unless told not to
            if static_id is None and not replicable.get("replicate"):
                replicable.roles.remote = Roles.none   
        
    def get_replicable_parents(self):
        '''Generator for the replicables without parents (base)'''
        for replicable in WorldInfo.subclass_of(Actor):
            if not replicable.parent:
                yield replicable  
    
    def register_actor(self, replicable):
        '''Registers replicable to physics system
        @param replicable: replicable to register'''
        collision_status = self.collision_listeners[replicable] = CollisionStatus(replicable)
        collision_status.on_start = partial(self.collision_dispatcher, replicable, True)
        collision_status.on_end = partial(self.collision_dispatcher, replicable, False)
        
        extrapolator = self.extrapolators[replicable] = PhysicsExtrapolator()
        
        # Static actors have existing world physics settings`
        if replicable._static:
            replicable.world_to_physics()
            
        # Non-static actors have physics to apply to world
        else:
            replicable.physics_to_world()

    def collision_dispatcher(self, replicable, new_collision, collided):
        '''Dispatches collision to replicables if they have permission to execute callback
        @param replicable: replicable object received notification
        @param new_collision: The status of collision
        @param collided: object replicable collided with'''
        # Determine which callback to run
        func = replicable.on_new_collision if new_collision else replicable.on_end_collision    
        
        if not replicable.registered:
            return
        
        # Ensure that the object exists
        is_actor = hasattr(collided, "instance_id")
        if is_actor and not collided.registered:
            return
        
        # Run callback
        try:
            func(collided)
        except TypeError as err:
            print(err, "\n")
    
    def add_extrapolation(self, replicable):
        extrapolator = self.extrapolators[replicable]
        extrapolator.update(replicable.physics) 
    
    def set_extrapolation_base(self, replicable, deltatime):
        if replicable.roles.local != Roles.simulated_proxy:
            return
        
        extrapolator = self.extrapolators[replicable]
        extrapolator.set_base(replicable.physics)       
    
    def post_physics_condition(self, replicable):
        '''Condition to update replicable after physics simulation
        @param replicable: replicable to check'''
        return replicable.roles.local >= Roles.simulated_proxy
    
    def post_update_condition(self, replicable):
        '''Condition to update replicable after replicable.update
        @param replicable: replicable to check'''
        return replicable.roles.local >= Roles.simulated_proxy
    
    def post_update(self, delta_time):
        '''Update the physics after actor changes
        @param delta_time: delta_time since last frame'''
        condition = self.post_update_condition
                
        for replicable in self.get_replicable_parents(): 
            # Get physics object
            physics = replicable.physics
            # If rigid body physics
            if physics.mode == Physics.none: 
                continue   
            
            replicable.physics_to_world(condition=condition, 
                                        deltatime=delta_time)
    
    def post_physics(self, delta_time):
        '''Update the physics after physics simulation is run
        @param delta_time: delta_time since last frame'''
        # Make short cut
        condition = condition=self.post_physics_condition
        
        # If any scene actors, we instantiate them
        if self.check_for_scene_actors:
            self.make_actors_from_scene()
            self.check_for_scene_actors = False
            
        # This operation would include these actors and set correct location
        for replicable in self.get_replicable_parents(): 
            # Get physics object
            physics = replicable.physics

            # If rigid body physics
            if physics.mode == Physics.none: 
                continue   
            
            # Apply the changes to the physics attributes
            replicable.world_to_physics(condition=condition, 
                                        deltatime=delta_time,
                                        post_callback=self.set_extrapolation_base)
        
        # Update controllers too
        for controller in WorldInfo.subclass_of(PlayerController):
            if hasattr(controller, "player_input"):
                controller.post_physics(delta_time)
                            
class InputSystem(System):
    
    def pre_update(self, delta_time):
        # Get keyboard and mouse events
        events = logic.keyboard.events.copy()
        events.update(logic.mouse.events)
        
        # Update all actors
        for replicable in WorldInfo.subclass_of(PlayerController):  
            
            if hasattr(replicable, "player_input"):
                replicable.player_input.update(events)
            
class Game(GameLoop):
    
    def __init__(self, addr="localhost", port=0):
        super().__init__(addr, port)
        print("Starting game...")
        
        self.physics = PhysicsSystem()
        self.inputs = InputSystem()
        self.last_time = monotonic()
        
        logic.getCurrentScene().post_draw.append(self.post_physics)
        
    def post_physics(self):
        ''' Additional support for post_physics callback'''
        delta_time = self.clock.last_delta_time
                
        for system in System:
            # Ensure system is active
            if system.active and hasattr(system, "post_physics"):
                system.post_physics(delta_time)
                # Update changes to replicable graph
                Replicable.update_graph() 
    
    @property
    def is_quit(self):
        return events.QKEY in logic.keyboard.active_events
            
    def quit(self):
        self.stop()
        raise QuitGame
    
    def update(self):
        # Check if we're to quit the game
        if self.is_quit:
            self.quit()
    
        # Update network
        super().update()
            