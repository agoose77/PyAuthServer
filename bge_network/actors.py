from network import Replicable, Attribute, Roles, Controller
from mathutils import Euler, Vector

from .enums import PhysicsType
from .bge_data import Armature, RigidBodyState

class PlayerController(Controller):
    pass

class Actor(Replicable):
    # Replicated attributes
    rigid_body_state = Attribute(RigidBodyState())
    physics = Attribute(PhysicsType.none)
    skeleton_name = Attribute("Suzanne_Skeleton")
    
    roles = Attribute(
                      Roles(Roles.authority, 
                            Roles.autonomous_proxy)
                      )
    
    def on_registered(self):
        super().on_registered()

        #self.skeleton = Armature(self.skeleton_name)
        self.update_simulated_physics = True
    
    
    def conditions(self, is_owner, is_complaint, is_initial):
        yield from super().conditions(is_owner, is_complaint, is_initial)
        
        remote_role = self.roles.remote
        
        # If simulated, send rigid body state
        if remote_role == Roles.simulated_proxy or remote_role == Roles.dumb_proxy or (self.roles.remote == Roles.autonomous_proxy and not is_owner):
            try:
                if self.update_simulated_physics or is_initial:
                    yield "rigid_body_state"
                    yield "physics"
            except AttributeError as e:
                import bge
                print(e, "s")
                bge.logic.endGame()

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
    #weapon = Attribute(type_of=Replicable)
    
    def on_notify(self, name):
        super().on_notify(name)
        
        if name == "flash_count":
            # play weapon effects
            pass
    
    def conditions(self, is_owner, is_complaint, is_initial):
        yield from super().conditions(is_owner, is_complaint, is_initial)
        
        if not is_owner:
            yield "flash_count"