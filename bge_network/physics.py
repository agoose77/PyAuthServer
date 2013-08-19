from .actors import Actor
from .enums import PhysicsType

from network import WorldInfo, Netmodes

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
        
    def update_physics(self, delta_time):
        pass
    
    def post_transform(self):
        for actor in WorldInfo.subclass_of(Actor):
            physics_mode = actor.physics
            
            if physics_mode == PhysicsType.none:
                continue
            
            physics = actor.rigid_body_state
            main_object = actor.skeleton
            if main_object is None:
                continue
        
            physics.position[:] = main_object.worldPosition
            physics.velocity[:] = main_object.worldLinearVelocity
            physics.angular[:] = main_object.worldAngularVelocity
            physics.rotation[:] = main_object.worldOrientation.to_euler()
    
class ClientPhysics(PhysicsSystem):
    
    def update(self, delta_time):
        for actor in WorldInfo.subclass_of(Actor):
            physics_mode = actor.physics
            physics = actor.rigid_body_state
            
            if physics_mode == PhysicsType.rigid_body:
                
                if physics.modified:
                    
                    main_object = actor.skeleton
                    
                    if main_object is None:
                        continue
                    
                    difference = physics.position - main_object.worldPosition
                    distance = difference.length_squared
                    
                    if distance > 4.0:
                        main_object.worldPosition = physics.position
                    
                    elif distance > 0.01:
                        main_object.worldPosition += difference * 0.1

                    main_object.worldLinearVelocity = physics.velocity
                    main_object.worldAngularVelocity = physics.angular
                    main_object.worldOrientation = physics.rotation
                
                    physics.modified = False
                
        self.update_physics(delta_time)
        self.post_transform()

class ServerPhysics(PhysicsSystem):
    
    def update(self, delta_time):
        for actor in WorldInfo.subclass_of(Actor):
            physics_mode = actor.physics
            physics = actor.rigid_body_state
            
            if physics_mode == PhysicsType.rigid_body:
                
                if physics.modified:
                    
                    main_object = actor.skeleton
                    if main_object is None:
                        continue
                    
                    main_object.worldPosition = physics.position
                    main_object.worldLinearVelocity = physics.velocity
                    main_object.worldAngularVelocity = physics.angular
                    main_object.worldOrientation = physics.rotation
                    
                    physics.modified = False
                
        self.update_physics(delta_time)
        self.post_transform()
