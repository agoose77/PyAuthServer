from .actors import Actor
from .enums import PhysicsType

from network import WorldInfo, Netmodes
from collections import defaultdict

from bge import logic
from functools import partial

class SimulationEntry:
    
    def __init__(self, actor, callback=None):
        self.callback = callback
        self.actor = actor
        
        self._duration = None
        self._func = None
    
    def set_func(self, func):
        self._func = func
    
    @property 
    def duration(self):
        return self._duration

    @duration.setter
    def duration(self, length):
        self._duration = length
        
        if length:
            self._func(length)

class PhysicsSystem:
    
    def __new__(cls, *args, **kwargs):
        """Constructor switch depending upon netmode"""
        if cls is PhysicsSystem:
            netmode = WorldInfo.netmode
            
            if netmode == Netmodes.server:
                return ServerPhysics.__new__(ServerPhysics, *args, **kwargs)
            
            elif netmode == Netmodes.client:
                return ClientPhysics.__new__(ClientPhysics,*args, **kwargs)
        else:
            return super().__new__(cls)
    
    def __init__(self, update_func, apply_func):
        self._exempt_actors = []        
        self._update_func = update_func
        self._apply_func = apply_func
        
    def add_exemption(self, actor):
        print("{} is exempt from default physics".format(actor))
        self._exempt_actors.append(actor)
    
    def remove_exemption(self, actor):
        self._exempt_actors.remove(actor)        
    
    def update_for(self, actor, delta_time):
        if actor.physics < PhysicsType.rigid_body:
            return
        
        self._update_func(delta_time)
        
        # Restore other objects
        for this_actor in WorldInfo.subclass_of(Actor):
            
            if this_actor == actor:
                continue

            this_actor.transform = this_actor.transform
        
        self._apply_func()
    
    def restore_objects(self):
        for actor in WorldInfo.subclass_of(Actor):
            if actor.physics < PhysicsType.rigid_body:
                actor.restore_physics()
    
    def update(self, scene, delta_time):        
        self._update_func(delta_time)
        
        # Restore scheduled objects
        for actor in self._exempt_actors:
            actor.restore_physics()

        self._apply_func()
        self.restore_objects()
        
        
class ServerPhysics(PhysicsSystem):
    
    def restore_objects(self):
        
        for actor in WorldInfo.subclass_of(Actor):
            
            if actor.physics < PhysicsType.rigid_body:
                actor.restore_physics()
                continue
            
            state = actor.rigid_body_state
            
            # Can probably do this once then use muteable property
            state.position = actor.position.copy()
            state.velocity = actor.velocity.copy()
            state.rotation = actor.rotation #.copy()
            state.angular = actor.angular.copy()
            
class ClientPhysics(PhysicsSystem):
    
    small_correction_squared = 0.2 ** 2
    
    def actor_replicated(self, actor, actor_physics):
        difference = actor_physics.position - actor.position
        
        if difference.length_squared < self.small_correction_squared:
            actor.position += difference * 0.2
            actor.velocity = actor_physics.velocity + difference * 0.8
            
        else:
            actor.position = actor_physics.position.copy()
            actor.velocity = actor_physics.velocity.copy()
        
        actor.rotation = actor_physics.rotation #.copy()
        actor.angular = actor_physics.angular.copy()
            
        