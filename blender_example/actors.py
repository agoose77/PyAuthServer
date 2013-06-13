from bge_network import Actor, PlayerController, InputManager
from network import WorldInfo, StaticValue, Attribute, RPC, Netmodes, Roles, reliable, simulated, LazyReplicableProxy
from bge import events
from mathutils import Vector
from math import pi
from time import monotonic

class RacingInputs(InputManager):
    mappings = {"forward": events.WKEY, "back": events.SKEY, "shift": events.MKEY, 'right': events.DKEY, 'left': events.AKEY}

class RacingController(PlayerController):
    
    input_class = RacingInputs
    
    @RPC
    def ServerMove(self, timestamp: StaticValue(float), in_accel: StaticValue(Vector), client_loc: StaticValue(Vector), 
                   forward: StaticValue(bool), back: StaticValue(bool), left: StaticValue(bool), right: StaticValue(bool)) -> Netmodes.server:
        pass
    
    @RPC
    def move(self, forward: StaticValue(bool), back: StaticValue(bool), left: StaticValue(bool), right: StaticValue(bool), timestamp: StaticValue(float)) -> Netmodes.server:
        
        move_speed = 10.0
        rotation_speed = pi / 60
        
        movement = (back - forward) * move_speed

        if isinstance(self.pawn.current_state, LadderVolume):
            velocity = Vector((0.000, 0.000, -movement))
            
        elif self.pawn.on_ground or self.pawn.time_airbourne < 0.05:
            velocity = Vector((movement, 0.000, self.pawn.physics.velocity.z))
            
        else:
            return
    
        self.pawn.worldAngularVelocity.zero()
        self.pawn.alignAxisToVect(Vector((0,0,1)), 2)
        
        self.pawn.physics.velocity = self.pawn.local_space(velocity)
        self.pawn.physics.orientation.z += (left - right) * rotation_speed 
    
    @RPC
    def shift(self) -> Netmodes.server:
        self.pawn.physics.position.z += 1
        self.pawn.physics.velocity.zero()
    
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
        
        if inputs.shift.active:
            self.shift()

class LadderVolume(Actor):
    obj_name = "LadderVolume"

class FloorMesh(Actor):
    obj_name = "Plane"

class Car(Actor):
    obj_name = "Cube"
    
    def on_create(self):
        super().on_create()
        
        self.allowed_transitions = [LadderVolume, FloorMesh]
        self.lift_time = 0.0
        self.physics.position.z = 3
        
        # Mark as simulated
        simulated(self.on_new_collision)
        simulated(self.on_end_collision)
    
    def on_transition(self, last, new):
        if isinstance(last, LadderVolume): 
            self.physics.velocity.zero() 
            
        if new is None:
            self.lift_time = monotonic()
            self.physics.velocity.zero()  
    
    @property
    def time_airbourne(self):
        return monotonic() - self.lift_time
    