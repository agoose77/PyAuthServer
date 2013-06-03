from bge_network import Actor, Physics, PlayerController, InputManager
from network import WorldInfo, StaticValue, Attribute, RPC, Replicable, Netmodes, Roles, reliable, simulated
from bge import events
from mathutils import Vector

class RacingInputs(InputManager):
    mappings = {"forward": events.WKEY, "back": events.SKEY, "shift": events.MKEY, 'die': events.DKEY}

class RacingController(PlayerController):
    input_class = RacingInputs
    
    def on_unregistered(self):
        super().on_unregistered()
    
    @RPC
    def move(self, forward: StaticValue(bool), back: StaticValue(bool), timestamp: StaticValue(float)) -> Netmodes.server:
        
        speed = 10.0
        velocity = Vector(((back - forward) * speed, 0.0, 0.0))
        self.pawn.physics.velocity = self.pawn.local_space(velocity)
    
    @RPC
    def shift(self) -> Netmodes.server:
        self.pawn.physics.position.x += 0.1
    
    @RPC
    def suicide(self) -> Netmodes.server:
        self.request_unregistration()
    
    def player_update(self, delta_time):
        
        if self.pawn.registered:
            timestamp = WorldInfo.elapsed
            
            inputs = self.player_input
            forward = inputs.forward.active
            back = inputs.back.active
            
            self.move(forward, back, timestamp)
            
            if inputs.shift.active:
                self.shift()
            
            if inputs.die.pressed:
                self.suicide()

class Car(Actor):
    mesh_name = "futuristic_car"
    
    