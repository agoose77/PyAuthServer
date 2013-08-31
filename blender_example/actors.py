from bge_network import PlayerController, ReplicableInfo, Replicable, Attribute, Roles, Pawn, simulated, WorldInfo, Netmodes, Weapon, WeaponAttachment
from mathutils import Vector, Euler
from math import radians

class GameReplicationInfo(ReplicableInfo):
    roles = Attribute(Roles(Roles.authority, Roles.simulated_proxy))
    
    time_to_start = Attribute(0.0)
    match_started = Attribute(False)
    
    def conditions(self, is_owner, is_complaint, is_initial):
        yield from super().conditions(is_owner, is_complaint, is_initial)

        yield "match_started"
        yield "time_to_start"
    
class LegendController(PlayerController):
    
    input_fields = "forward", "backwards", "left", "right", "shoot"
        
    def execute_move(self, inputs, mouse_diff_x, mouse_diff_y, delta_time):
        y_plane = inputs.forward.active - inputs.backwards.active
        x_plane = inputs.right.active - inputs.left.active
        
        forward_speed = 4.0
        turn_speed = 20
        look_speed = 1
        look_limit = radians(45)
        
        forward = forward_speed * y_plane
        side = forward_speed * x_plane
        
        velocity = Vector((side, forward, 0.0))
        velocity.length = forward_speed
        
        epsilon = 0.001
        nearly_zero = 0.00001
        
        if abs(mouse_diff_x) < epsilon:
            mouse_diff_x = nearly_zero
        if abs(mouse_diff_y) < epsilon:
            mouse_diff_x = nearly_zero
        
        angular = Vector((0, 0, mouse_diff_x * turn_speed))
        
        self.pawn.view_pitch = max(0.0, min(look_limit, self.pawn.view_pitch + mouse_diff_y * look_speed))
        self.pawn.velocity.xy = velocity.xy
        self.pawn.angular = angular
        self.camera.rotation = Euler(( radians(90) + self.pawn.view_pitch, 0, 0))

        WorldInfo.physics.update_for(self.pawn, delta_time)

class RobertNeville(Pawn):
    entity_name = "Suzanne_Physics"      
        
class M4A1Weapon(Weapon):
    
    def on_initialised(self):
        super().on_initialised()
        
        self.sound_path = "sounds"
        self.max_ammo = 50
        self.attachment_class = M4A1Attachment
        self.shoot_interval = 0.5
    
class M4A1Attachment(WeaponAttachment):
    
    entity_name = "M4"