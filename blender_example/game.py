from network import GameLoop, WorldInfo, Roles, is_simulated, System, BaseController
from bge import events, logic

from errors import QuitGame
from actors import Actor
from enums import Physics

from time import time
from random import randint
from collections import defaultdict

def random_spawn(n):
    '''Spawns randomly positioned actors'''
    for i in range(n):
        a = Actor()
        a.physics.position[:] = randint(-10, 10), randint(-10, 10), 20

class InputSystem(System):
    
    def pre_update(self, delta_time):
        
        for replicable in WorldInfo.actors:
            if hasattr(replicable, "player_input") and isinstance(replicable, BaseController):
                replicable.player_input = True
        
class PhysicsSystem(System):
    
    def post_update(self, delta_time):
        # Update all actors
        for replicable in WorldInfo.actors:  
            
            if not isinstance(replicable, Actor):
                continue
            
            # Get physics object
            physics = replicable.physics
               
            # If rigid body physics
            if physics.mode != Physics.rigidbody: 
                continue 
            
            # Get timestamp
            #time_sent = physics.timestamp
            
            # Constantly correcting (fixes issue if using loc movement)
            if replicable.local_role == Roles.simulated_proxy:
                # This is no longer valid due to clock sync issues.

                projected = physics.position + (physics.velocity * delta_time)
                position_delta = projected - replicable.worldPosition 
           
                if position_delta.length < 0.5:
                    replicable.worldLinearVelocity = position_delta + physics.velocity
                    
                else:
                    replicable.worldLinearVelocity = position_delta * .4 + physics.velocity
                    replicable.worldPosition += position_delta * .1
                

            elif replicable.local_role == Roles.authority:
                # Reflect initial displacement 
                if physics.timestamp == 0.000:
                    replicable.worldPosition = physics.position
                    physics.timestamp=1.0
                    replicable.worldLinearVelocity = physics.velocity
                    print("init")
                
                # Update physics with replicable position, velocity and timestamp    
                physics.position = replicable.worldPosition
                physics.velocity = replicable.worldLinearVelocity
                #physics.timestamp = current_time
            
class Game(GameLoop):
    
    def __init__(self, addr="localhost", port=0):
        super().__init__(addr, port)
        
        self.physics = PhysicsSystem()
        self.inputs = InputSystem()
        self.last_time = time()
        
    @property
    def is_quit(self):
        key = events.QKEY
        active_events = getattr(logic.keyboard, 'active_events')
        return key in active_events  
    
    def update(self):
        
        if self.is_quit:
            self.stop()
            raise QuitGame
                
        # Update network
        super().update()