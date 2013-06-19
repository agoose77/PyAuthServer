from network import GameLoop, Replicable, WorldInfo, Roles, System, is_simulated, keyeddefaultdict, allowed_to_run

from bge import logic, events, types
import sys; sys.path.append(logic.expandPath("//../"))

from .errors import QuitGame
from .actors import Actor, PlayerController
from .enums import Physics

from time import monotonic
from functools import partial
from collections import deque

class CollisionStatus:    
    
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
        self._old_colliders = self._new_colliders.copy()
        self._new_colliders.clear()
        
        for obj in difference:
            self._registered.remove(obj)
            self.on_end(obj)
    
class JitterBuffer:
    
    def __init__(self, min_length=2, max_length=8):
        self.accumulator = 0.0
        self.last_time = None
        self.offset = 0.0
        self.queue = deque()
    
    def __len__(self):
        return len(self.queue)
    
    @property
    def latest(self):
        return self.queue[0]
    
    def populate(self, data):
        if not data in self.queue:
            self.queue.append(data)

    def validate_buffer(self, delta_time):
        '''Handles the buffer offset'''
        
        # Get the length of the offset queue
        queue_length = len(self.queue)
        
        is_moving = False
        
        try:
            is_moving = self.latest.moving
        except IndexError:
            pass
        
        if is_moving:
            if queue_length < self.min_length and queue_length:
                self.offset -= delta_time * 0.01
            
            # Enforce upper bound on offset queue
            elif queue_length > self.max_length:
                # Will cause recalculation of offset
                self.offset += delta_time * 0.01
            
        elif not queue_length:
            self.last_time = None
            return
            
        return True
        
    def get(self, delta_time):
        self.accumulator += delta_time*2
        
        # Allow for buffer resizing
        if not self.validate_buffer(delta_time):
            return
        
        # Get the timestamp it was intended for
        target_time = self.latest.timestamp
        
        try:
            # Offset oldest entry time by buffer latency and accumulator
            relative_time = self.last_time + self.accumulator + self.offset
            
        except TypeError:
            # If the last time is None use latest data
            self.last_time = target_time
            # Avoid build up accumulation time
            self.accumulator = 0.0
            return
        
        # Get the difference (positive = add to accum)
        additional_time = relative_time - target_time
        
        # If it's still old relative to buffer "current" time
        if additional_time < 0.0:
            return
        
        # Add the additional time to the accumulator
        self.accumulator = additional_time
        # Store the last time
        self.last_time = target_time
        # Remove from buffer
        return self.queue.popleft()
                
class PhysicsSystem(System):
    
    def __init__(self):
        super().__init__()
        
        self.cache = keyeddefaultdict(self.register_object)
        self.collision_listeners = {}
        self.make_actors_from_scene()
    
    def make_actors_from_scene(self):
        scene = logic.getCurrentScene()
        
        for obj in scene.objects:
            try:
                cls_name = obj['actor']
                static_id = obj.get('static_id')
                
            except KeyError:
                continue
            
            cls = Replicable.from_type_name(cls_name)
            
            if not issubclass(cls, Actor):
                continue
            
            is_sensor = obj.physicsType in (logic.KX_PHYSICS_SENSOR, logic.KX_PHYSICS_ACTOR_SENSOR)
            
            if not (obj.mass or is_sensor):
                print("Static actor  {} does not have correct physics".format(obj))
                continue
            
            # Make static actor            
            replicable = cls(object=obj, instance_id=static_id)
            # Copy existing physics
            replicable.physics.position = replicable.worldPosition.copy()
            
            if static_id is None:
                replicable.roles.remote = Roles.none
            
    def register_object(self, replicable):
        jitter_buffer = JitterBuffer()
        
        collision_status = self.collision_listeners[replicable] = CollisionStatus(replicable)
        collision_status.on_start = partial(self.collision_dispatcher, replicable, True)
        collision_status.on_end = partial(self.collision_dispatcher, replicable, False)
        
        if replicable._static:
            replicable.physics.position = replicable.worldPosition.copy()
        else:
            replicable.worldPosition = replicable.physics.position

        return jitter_buffer
    
    def collision_dispatcher(self, replicable, new_collision, collided):
        func = replicable.on_new_collision if new_collision else replicable.on_end_collision    
        if allowed_to_run(replicable, func):
            
            func(collided)
            
            if replicable.roles.local != Roles.autonomous_proxy:
                self.physics_to_world(replicable)
        
    def physics_to_world(self, replicable):
        physics = replicable.physics
        
        replicable.worldPosition = physics.position
        replicable.worldLinearVelocity = physics.velocity
        replicable.worldOrientation = physics.orientation
    
    def world_to_physics(self, replicable):
        physics = replicable.physics
        
        physics.position = replicable.worldPosition
        physics.velocity = replicable.worldLinearVelocity
        physics.orientation = replicable.worldOrientation.to_euler()
        physics.timestamp = WorldInfo.elapsed
        
    def pre_replication(self, delta_time):
        '''Update the physics before actor updating
        @param delta_time: delta time since last frame'''
        role_authority = Roles.authority
        role_simulated = Roles.simulated_proxy
        
        for replicable in WorldInfo.subclass_of(Actor):  
            
            # Get physics object
            physics = replicable.physics
               
            # If rigid body physics
            if physics.mode != Physics.rigidbody: 
                continue 
            
            jitter_buffer = self.cache[replicable]   
            
            if replicable.roles.local == role_authority:   
                self.world_to_physics(replicable)
            
            # Or run simulation before actors update on client
            elif replicable.roles.local == role_simulated:
                # Determine how far from reality we are
                current_position = replicable.worldPosition
                new_data = physics

                difference = new_data.position - current_position
                
                offset = new_data.velocity.length * delta_time
                
                threshold = 0.1
                
                if difference.length > threshold:
                    replicable.worldPosition += difference * 0.4   
                    replicable.worldLinearVelocity = new_data.velocity
                    
                replicable.worldLinearVelocity = new_data.velocity
                replicable.worldOrientation = physics.orientation   
                
    def post_update(self, delta_time):
        '''Update the physics after actor changes
        @param delta_time: delta_time since last frame'''
        # Update all actors
        for replicable in WorldInfo.subclass_of(Actor):  
            
            # Get physics object
            physics = replicable.physics
               
            # If rigid body physics
            if physics.mode != Physics.rigidbody: 
                continue 

            jitter_buffer = self.cache[replicable]            

            if replicable.roles.local == Roles.authority:
                # Update physics with replicable position, velocity and timestamp    
                self.physics_to_world(replicable)
          
class InputSystem(System):
    
    def pre_update(self, delta_time):
        # Get keyboard and mouse events
        events = logic.keyboard.events.copy();events.update(logic.mouse.events)
        
        # Update all actors
        for replicable in WorldInfo.subclass_of(PlayerController):  
            
            if hasattr(replicable, "player_input"):
                replicable.player_input.update(events)
            
class Game(GameLoop):
    
    def __init__(self, addr="localhost", port=0):
        super().__init__(addr, port)
        
        self.physics = PhysicsSystem()
        self.inputs = InputSystem()
        self.last_time = monotonic()
        
    @property
    def is_quit(self):
        return events.QKEY in logic.keyboard.active_events
            
    def quit(self):
        self.stop()
        raise QuitGame
    
    def update(self):
        
        if self.is_quit:
            self.quit()
      
        # Update network
        super().update()
            