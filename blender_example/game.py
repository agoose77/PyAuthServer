from network import GameLoop, WorldInfo, Roles, System
from bge import events, logic

from errors import QuitGame
from actors import Actor
from enums import Physics

from time import time
from random import randint
from collections import defaultdict, deque

def random_spawn(n):
    '''Spawns randomly positioned actors'''
    for i in range(n):
        a = Actor()
        a.physics.position[:] = randint(-10, 10), randint(-10, 10), 20

class JitterBuffer:
    
    def __init__(self, min_length=2, max_length=8):
        self.max_length = max_length
        self.min_length = min_length
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
        
        self.cache = defaultdict(JitterBuffer)
        self.comparable = defaultdict(lambda: None)
        
    def pre_update(self, delta_time):
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
            
            # Before the Actors are aware, set the initial position
            if replicable.local_role == role_authority:   
                
                try:
                    latest = jitter_buffer.latest
                except IndexError:
                    # Initial set from object data
                    replicable.worldPosition = physics.position
                    replicable.worldLinearVelocity = physics.velocity
                    jitter_buffer.populate(physics)
            
            # Or run simulation before actors update on client
            elif replicable.local_role == role_simulated:
                current_data = self.comparable[replicable]

                # If the replicated physics has changed 
                if current_data is not physics:
                    self.comparable[replicable] = physics
                    jitter_buffer.populate(physics)
                
                # Run through jitter buffer first
                new_data = jitter_buffer.get(delta_time)
                                
                # If we're not allowed to pull data
                if new_data is None:
                    continue
                
                # Determine how far from reality we are
                current_position = replicable.worldPosition
                
                difference = new_data.position - current_position
                
                offset = new_data.velocity.length * delta_time
                
                threshold = 0.4
                
                if difference.length < threshold:                
                    replicable.worldLinearVelocity = new_data.velocity + difference    
                    
                elif difference.length > threshold:
                    replicable.worldPosition = new_data.position   
                    replicable.worldLinearVelocity = new_data.velocity
                    
                replicable.worldLinearVelocity = new_data.velocity + difference       
            
    
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

            if replicable.local_role == Roles.authority:
                # Update physics with replicable position, velocity and timestamp    
                physics.position = replicable.worldPosition
                physics.velocity = replicable.worldLinearVelocity
                physics.timestamp = WorldInfo.elapsed
            
class Game(GameLoop):
    
    def __init__(self, addr="localhost", port=0):
        super().__init__(addr, port)
        
        self.physics = PhysicsSystem()
        self.last_time = time()
        
    @property
    def is_quit(self):
        key = events.QKEY
        active_events = getattr(logic.keyboard, 'active_events')
        return key in active_events  
    
    def quit(self):
        self.stop()
        raise QuitGame
    
    def update(self):
        
        if self.is_quit:
            self.quit()
                
        # Update network
        super().update()