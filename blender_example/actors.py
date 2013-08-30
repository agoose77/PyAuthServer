from bge_network import PlayerController
from mathutils import Vector

class ExampleController(PlayerController):
    
    def get_acceleration(self, inputs):
        y_plane = inputs.forward.active - inputs.backwards.active
        x_plane = inputs.right.active - inputs.left.active
        
        forward_speed = 4.0
        turn_speed = 2.0
        
        forward = forward_speed * y_plane
        side = forward_speed * x_plane
        
        velocity = Vector((side, forward, 0.0))
        velocity.length = forward_speed
        
        angular = Vector()
        
        return velocity, angular