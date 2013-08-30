from bge_network import PlayerController, ReplicableInfo, Replicable, Attribute, Roles, simulated, WorldInfo, StaticValue, InputManager, Netmodes
from mathutils import Vector, Euler

class GameReplicationInfo(ReplicableInfo):
    roles = Attribute(Roles(Roles.authority, Roles.simulated_proxy))
    
    time_to_start = Attribute(0.0)
    match_started = Attribute(False)
    
    def conditions(self, is_owner, is_complaint, is_initial):
        yield from super().conditions(is_owner, is_complaint, is_initial)

        yield "match_started"
        yield "time_to_start"
    
class ExampleController(PlayerController):
    
    input_fields = "forward", "backwards", "left", "right", "shoot"
        
    def execute_move(self, inputs, mouse_diff_x, mouse_diff_y, delta_time):
        y_plane = inputs.forward.active - inputs.backwards.active
        x_plane = inputs.right.active - inputs.left.active
        
        forward_speed = 4.0
        turn_speed = 20
        
        forward = forward_speed * y_plane
        side = forward_speed * x_plane
        
        velocity = Vector((side, forward, 0.0))
        velocity.length = forward_speed
        
        angular = Vector((0, 0, mouse_diff_x * turn_speed))
        
        self.pawn.velocity.xy = velocity.xy
        self.pawn.angular = angular

        WorldInfo.physics.update_for(self.pawn, delta_time)