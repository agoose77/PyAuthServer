from network import Replicable, Attribute, Roles, Controller, WorldInfo, Netmodes, StaticValue
from mathutils import Euler, Vector

from configparser import ConfigParser, ExtendedInterpolation
from inspect import getmembers
from bge import logic, events

from .enums import PhysicsType
from .bge_data import Armature, RigidBodyState
from .inputs import InputManager

class PlayerController(Controller):
    
    input_fields = ["forward", "backwards", "left", "right"]
    
    def load_keybindings(self):
        all_events = {x[0]: str(x[1]) for x in getmembers(events) if isinstance(x[1], int)}
        
        filepath = logic.expandPath("//inputs.conf")
        
        parser = ConfigParser(defaults=all_events, interpolation=ExtendedInterpolation())
        
        parser.read(filepath)
        
        # Read binding information
        bindings = {k: eval(v) for k, v in parser[self.__class__.type_name].items() if not k.upper() in all_events}
        
        # Ensure we have all bindings
        assert(set(self.input_fields).issubset(bindings))
        
        print("Loaded {} keybindings".format(len(bindings)))
        
        return bindings
    
    def on_registered(self):
        super().on_registered()
        
        if WorldInfo.netmode != Netmodes.client:
            return
        
        self.inputs = InputManager(self.load_keybindings())
        self.player_update(1)
        print("Created input manager")
    
    def server_move(self, inputs:StaticValue(InputManager, fields=input_fields), 
                    delta_time:StaticValue(float)) -> Netmodes.server:
        pass
    
    def player_update(self, delta_time):
        self.server_move(self.inputs, delta_time)
    

class Actor(Replicable):
    # Replicated attributes
    rigid_body_state = Attribute(RigidBodyState())
    physics          = Attribute(PhysicsType.none)
    roles            = Attribute(
                          Roles(Roles.authority, 
                                Roles.autonomous_proxy)
                          )
    
    skeleton_name = "Suzanne_Skeleton"
    
    def on_registered(self):
        super().on_registered()
        
        self.skeleton = Armature(self.skeleton_name)
        self.update_simulated_physics = True
    
    def conditions(self, is_owner, is_complaint, is_initial):
        yield from super().conditions(is_owner, is_complaint, is_initial)
        
        remote_role = self.roles.remote
        
        # If simulated, send rigid body state
        if remote_role == Roles.simulated_proxy or remote_role == Roles.dumb_proxy or (self.roles.remote == Roles.autonomous_proxy and not is_owner):
      
            if self.update_simulated_physics or is_initial:
                yield "rigid_body_state"
                yield "physics"

class WeaponAttatchment(Actor):
    mesh_name = ""
    
    def on_registration(self):
        super().on_registration()
        
        self.mesh = Armature(self.mesh_name)

class Weapon(Actor):
    attachment_class = None
    
    def on_registration(self):
        super().on_registration()
        
        self.attatchment = self.attachment_class()
        
class Pawn(Actor):
    flash_count = Attribute(0, notify=True)
    physics =     Attribute(PhysicsType.rigid_body)
    
    def on_notify(self, name):
        super().on_notify(name)
        
        if name == "flash_count":
            # play weapon effects
            pass
    
    def conditions(self, is_owner, is_complaint, is_initial):
        yield from super().conditions(is_owner, is_complaint, is_initial)
        
        if not is_owner:
            yield "flash_count"