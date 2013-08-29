from network import Replicable, Attribute, Roles, Controller, WorldInfo, Netmodes, StaticValue, NetmodeOnly
from mathutils import Euler, Vector

from configparser import ConfigParser, ExtendedInterpolation
from inspect import getmembers
from bge import logic, events
from collections import namedtuple, OrderedDict

from .enums import PhysicsType
from .bge_data import Armature, RigidBodyState, GameObject
from .inputs import InputManager

SavedMove = namedtuple("Move", ("position", "rotation", "velocity", "angular", "delta_time", "inputs"))

class PlayerReplicationInfo(Replicable):
    
    name = Attribute("")

class PlayerController(Controller):
    
    input_fields = ["forward", "backwards", "left", "right"]
    info = Attribute(type_of=Replicable)
    
    move_error_limit = 0.4 ** 2 
    
    @NetmodeOnly(Netmodes.client)
    def load_keybindings(self):
        all_events = {x[0]: str(x[1]) for x in getmembers(events) if isinstance(x[1], int)}        
        filepath = logic.expandPath("//inputs.conf")        
        parser = ConfigParser(defaults=all_events, interpolation=ExtendedInterpolation())        
        parser.read(filepath)        
        
        # Read binding information
        bindings = {k: eval(v) for k, v in parser[self.__class__.type_name].items() if not k.upper() in all_events and k in self.input_fields}        
        
        # Ensure we have all bindings
        assert(set(self.input_fields).issubset(bindings))        
        
        print("Loaded {} keybindings".format(len(bindings)))   
            
        return bindings
    
    @NetmodeOnly(Netmodes.client)
    def setup_input(self):
        keybindings = self.load_keybindings()
        self.inputs = InputManager(keybindings)
        print("Created input manager")
        
    def possess(self, actor):
        super().possess(actor)
        
        WorldInfo.physics.add_exemption(actor)
    
    def unpossess(self):
        WorldInfo.physics.remove_exemption(self.pawn)
        
        super().unpossess()
        
    def on_registered(self):
        super().on_registered()
        
        self.setup_input()

        self.current_move_id = 0
        self.previous_moves = OrderedDict()
        
    def execute_move(self, inputs, delta_time):
        vel = Vector((0, inputs.forward.active, self.pawn.velocity.z))
        ang = Vector()
        
        self.pawn.velocity.xy = vel.xy
        self.pawn.angular = ang

        WorldInfo.physics.update_for(self.pawn, delta_time)
    
    def save_move(self, move_id, delta_time, input_tuple):
        self.previous_moves[move_id] = SavedMove(self.pawn.position.copy(), self.pawn.rotation.copy(), 
                                                              self.pawn.velocity.copy(), self.pawn.angular.copy(), 
                                                              delta_time, input_tuple)
    
    def get_corrected_state(self, position, rotation):
        
        pos_difference = self.pawn.position - position
        
        if pos_difference.length_squared < self.move_error_limit:
            return
        
        # Create correction if neccessary
        correction = RigidBodyState()
        
        correction.position = self.pawn.position
        correction.rotation = self.pawn.rotation
        correction.velocity = self.pawn.velocity
        correction.angular = self.pawn.angular
        
        return correction
        
    def server_validate(self, move_id:StaticValue(int), 
                    inputs: StaticValue(InputManager, fields=input_fields), 
                    delta_time: StaticValue(float),
                    position: StaticValue(Vector),
                    rotation: StaticValue(Euler)) -> Netmodes.server:
        
        self.current_move_id = move_id       
         
        self.execute_move(inputs, delta_time)
        
        self.save_move(move_id, delta_time, inputs.to_tuple())
        
        correction = self.get_corrected_state(position, rotation)

        if correction is None:
            self.acknowledge_good_move(self.current_move_id)
            
        else:
            self.correct_bad_move(self.current_move_id, correction)
            
    def acknowledge_good_move(self, move_id: StaticValue(int)) -> Netmodes.client:
        try:
            self.previous_moves.pop(move_id)
        except KeyError:
            print("Couldn't remove key for some reason")
            return

        additional_keys = [k for k in self.previous_moves if k < move_id]
        for key in additional_keys:
            self.previous_moves.pop(key)
    
    def correct_bad_move(self, move_id: StaticValue(int), correction: StaticValue(RigidBodyState)) -> Netmodes.client:
        self.acknowledge_good_move(move_id)

        self.pawn.position = correction.position
        self.pawn.velocity = correction.velocity
        self.pawn.rotation = correction.rotation
        self.pawn.angular = correction.angular
   
        lookup_dict = {}
        
        with self.inputs.using_interface(lookup_dict):
        
            for move_id, move in self.previous_moves.items():
                # Restore inputs
                lookup_dict.update(zip(sorted(self.inputs.keybindings), move.inputs))
                # Execute move
                self.execute_move(self.inputs, move.delta_time)
                self.save_move(move_id, move.delta_time, move.inputs)
                
    def player_update(self, delta_time):
        if not self.pawn:
            return
        
        self.execute_move(self.inputs, delta_time)
        self.server_validate(self.current_move_id, self.inputs, delta_time, self.pawn.position, self.pawn.rotation)
        
        self.save_move(self.current_move_id, delta_time, self.inputs.to_tuple())

        self.current_move_id += 1
        if self.current_move_id == 255:
            self.current_move_id = 0
                
class Actor(Replicable):

    rigid_body_state = Attribute(RigidBodyState(), notify=True)
    physics          = Attribute(PhysicsType.none)
    roles            = Attribute(
                          Roles(
                                Roles.authority, 
                                Roles.autonomous_proxy
                                )
                          )
    
    actor_name = ""
    
    def on_registered(self):
        super().on_registered()
        
        self.object = GameObject(self.actor_name)
        self.update_simulated_physics = True
    
    def on_notify(self, name):
        if name == "rigid_body_state":
            WorldInfo.physics.actor_replicated(self, self.rigid_body_state)
            
        else:
            super().on_notify(name)
            
    
    def conditions(self, is_owner, is_complaint, is_initial):
        yield from super().conditions(is_owner, is_complaint, is_initial)
        
        remote_role = self.roles.remote

        # If simulated, send rigid body state
        if (remote_role == Roles.simulated_proxy) or (remote_role == Roles.dumb_proxy) or (self.roles.remote == Roles.autonomous_proxy and not is_owner):
            
            if self.update_simulated_physics or is_initial:
                
                yield "rigid_body_state"
                yield "physics"
    
    def restore_physics(self):
        self.object.worldTransform = self.object.worldTransform
        self.object.worldLinearVelocity = self.object.worldLinearVelocity
        self.object.worldAngularVelocity = self.object.worldAngularVelocity
    
    @property
    def transform(self):
        return self.object.localTransform
    
    @transform.setter
    def transform(self, val):
        self.object.localTransform = val
    
    @property
    def rotation(self):
        return self.object.localOrientation.to_euler()
    
    @rotation.setter
    def rotation(self, rot):
        self.object.localOrientation = rot
    
    @property
    def position(self):
        return self.object.localPosition
    
    @position.setter
    def position(self, pos):
        self.object.localPosition = pos
    
    @property
    def velocity(self):
        return self.object.localLinearVelocity
    
    @velocity.setter
    def velocity(self, vel):
        self.object.localLinearVelocity = vel
        
    @property
    def angular(self):
        return self.object.localAngularVelocity
    
    @angular.setter
    def angular(self, vel):
        self.object.localAngularVelocity = vel
    
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
    physics = Attribute(PhysicsType.rigid_body)
    
    actor_name = "Suzanne_Physics"
    
    def on_notify(self, name):
        # play weapon effects
        if name == "flash_count":
            pass
        else:
            super().on_notify(name)
                
    def conditions(self, is_owner, is_complaint, is_initial):
        yield from super().conditions(is_owner, is_complaint, is_initial)
        
        if not is_owner:
            yield "flash_count"