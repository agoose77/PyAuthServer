from bge_network import Actor, Physics, PlayerController, InputManager, PhysicsData
from network import WorldInfo, StaticValue, Attribute, RPC, Replicable, Netmodes, Roles, reliable, simulated
from bge import events
from mathutils import Vector

class RacingInputs(InputManager):
    mappings = {"forward": events.WKEY, "back": events.SKEY, "shift": events.MKEY, 'die': events.DKEY}

class RacingController(PlayerController):
    input_class = RacingInputs
    
    @RPC
    def ServerMove(self, timestamp: StaticValue(float), in_accel: StaticValue(Vector), client_loc: StaticValue(Vector), 
                   forward: StaticValue(bool), back: StaticValue(bool), left: StaticValue(bool), right: StaticValue(bool)) -> Netmodes.server:
        pass
    
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
    mesh_name = "Cube"
   # physics = Attribute(PhysicsData(Physics.none))
   
    def on_collision(self, obj):
        print("Collided with", obj)
   
    @simulated
    def update(self, dt):
        #print(self.worldScale)
        self.mass = 123
        pass