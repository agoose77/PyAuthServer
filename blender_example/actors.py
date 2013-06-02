from bge_network import Actor, Physics, PlayerController, InputManager
from network import WorldInfo, StaticValue, Attribute, RPC, Replicable, Netmodes, Roles, reliable, simulated

from bge import events
from mathutils import Vector

class RacingInputs(InputManager):
    mappings = {"forward": events.WKEY, "back": events.SKEY, "shift": events.MKEY, 'die': events.DKEY}

class RacingController(PlayerController):
    input_class = RacingInputs
    
    @RPC
    def move(self, forward: StaticValue(bool), back: StaticValue(bool), timestamp: StaticValue(float)) -> Netmodes.server:
        
        speed = 10.0
        velocity = Vector(((back - forward) * speed, 0.0, 0.0))
        self.pawn.physics.velocity = self.pawn.local_space(velocity)
    
    @RPC
    def shift(self) -> Netmodes.server:
        self.pawn.physics.position.x += 0.1
        
    def player_update(self, delta_time):
        
        if self.pawn:
            timestamp = WorldInfo.elapsed
            
            inputs = self.player_input
            forward = inputs.forward.active
            back = inputs.back.active
            
            self.move(forward, back, timestamp)
            
            if inputs.shift.active:
                self.shift()
            
            if inputs.die.pressed:
                print(self._instances)
                #self.pawn.request_unregistration()

class Car(Actor):
    mesh_name = "futuristic_car"
    
    #target = Attribute(type_of=Replicable, notify=True)
    
    #remote_role = Roles.autonomous_proxy
        
    def on_notify(self, name):
        if name == "target":
            self.changed_target(self.target)
        else:
            super().on_notify(name)
    
    def conditions(self, is_owner, is_complain, is_initial):
        yield from super().conditions(is_owner, is_complain, is_initial)
        
#        if complain:
#            yield "target"
            
    def changed_target(self, target):
        pass
    
    
    