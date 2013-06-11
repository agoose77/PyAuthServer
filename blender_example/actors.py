from bge_network import Actor, Physics, PlayerController, InputManager, PhysicsData
from network import WorldInfo, StaticValue, Attribute, RPC, Replicable, Netmodes, Roles, reliable, simulated
from bge import events
from mathutils import Vector
from math import pi

class RacingInputs(InputManager):
    mappings = {"forward": events.WKEY, "back": events.SKEY, "shift": events.MKEY, 'right': events.DKEY, 'left': events.AKEY}

class RacingController(PlayerController):
    
    input_class = RacingInputs
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
    
    @RPC
    def ServerMove(self, timestamp: StaticValue(float), in_accel: StaticValue(Vector), client_loc: StaticValue(Vector), 
                   forward: StaticValue(bool), back: StaticValue(bool), left: StaticValue(bool), right: StaticValue(bool)) -> Netmodes.server:
        pass
    
    @RPC
    def move(self, forward: StaticValue(bool), back: StaticValue(bool), left: StaticValue(bool), right: StaticValue(bool), timestamp: StaticValue(float)) -> Netmodes.server:
        
        move_speed = 10.0
        rotation_speed = pi / 60
        
        velocity = Vector(((back - forward) * move_speed, 0.0, 0.0))
        self.pawn.physics.velocity = self.pawn.local_space(velocity)
        self.pawn.physics.orientation.z += (left - right) * rotation_speed 
    
    @RPC
    def shift(self) -> Netmodes.server:
        self.pawn.physics.position.z += 1.1
    
    @RPC
    def suicide(self) -> Netmodes.server:
        self.request_unregistration()
    
    def player_update(self, delta_time):
        if not self.pawn.registered:
            return 
        
        timestamp = WorldInfo.elapsed
        inputs = self.player_input
        
        forward = inputs.forward.active
        back = inputs.back.active
        left = inputs.left.active
        right = inputs.right.active
        
        self.move(forward, back, left, right, timestamp)
        
        if inputs.shift.pressed:
            self.shift()

class Car(Actor):
    mesh_name = "Cube"
    
    @simulated
    def on_new_collision(self, obj):
        print("Collided with", obj)
    
    @simulated
    def update(self, dt):
        pass