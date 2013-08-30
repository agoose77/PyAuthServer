from network import Replicable, Attribute, Roles, Controller, ReplicableInfo, WorldInfo, simulated, Netmodes, StaticValue, NetmodeOnly
from mathutils import Euler, Vector, Matrix

from configparser import ConfigParser, ExtendedInterpolation
from inspect import getmembers
from bge import logic, events, render
from collections import namedtuple, OrderedDict
from math import pi

from .enums import PhysicsType
from .bge_data import RigidBodyState, GameObject, CameraObject
from .inputs import InputManager

SavedMove = namedtuple("Move", ("position", "rotation", "velocity", "angular", "delta_time", "inputs", "mouse_x", "mouse_y"))

class PlayerReplicationInfo(ReplicableInfo):
    
    name = Attribute("")

class PlayerController(Controller):
    
    input_fields = []
    
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
    
    def setup_camera(self, camera):
        camera_socket = self.pawn.sockets['camera']     
        camera.parent_to(camera_socket)
        camera.position = Vector()
        camera.rotation = Euler((pi / 2, 0, 0))
    
    def set_camera(self, camera):   
        super().set_camera(camera)
        
        self.setup_camera(camera)
                    
    def possess(self, actor):
        WorldInfo.physics.add_exemption(actor)
        
        super().possess(actor)
    
    def on_initialised(self):
        super().on_initialised()
                
        self.setup_input()

        self.current_move_id = 0
        self.previous_moves = OrderedDict()
        
        self.mouse_setup = False
        self.camera_setup = False
        
    def unpossess(self):
        WorldInfo.physics.remove_exemption(self.pawn)
        
        super().unpossess()
            
    def on_unregistered(self):
        super().on_unregistered()
        
        if self.pawn:
            self.pawn.request_unregistration()
            self.camera.request_unregistration()
            
            self.remove_camera()
            self.unpossess()
    
    def execute_move(self, inputs, mouse_diff_x, mouse_diff_y, delta_time):
        vel, ang = Vector(), Vector()
        
        self.pawn.velocity.xy = vel.xy
        self.pawn.angular = ang

        WorldInfo.physics.update_for(self.pawn, delta_time)
    
    def save_move(self, move_id, delta_time, input_tuple, mouse_diff_x, mouse_diff_y):
        self.previous_moves[move_id] = SavedMove(self.pawn.position.copy(), self.pawn.rotation.copy(), 
                                                  self.pawn.velocity.copy(), self.pawn.angular.copy(), 
                                                  delta_time, input_tuple, mouse_diff_x, mouse_diff_y)
    
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
                    inputs: StaticValue(InputManager, class_data={"fields": "input_fields"}), 
                    mouse_diff_x: StaticValue(float),
                    mouse_diff_y: StaticValue(float),
                    delta_time: StaticValue(float),
                    position: StaticValue(Vector),
                    rotation: StaticValue(Euler)) -> Netmodes.server:
        
        self.current_move_id = move_id       
         
        self.execute_move(inputs, mouse_diff_x, mouse_diff_y, delta_time)
        
        self.save_move(move_id, delta_time, inputs.to_tuple(), mouse_diff_x, mouse_diff_y)
        
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
        
        print("Correcting ... ")
        
        with self.inputs.using_interface(lookup_dict):
        
            for move_id, move in self.previous_moves.items():
                # Restore inputs
                lookup_dict.update(zip(sorted(self.inputs.keybindings), move.inputs))
                # Execute move
                self.execute_move(self.inputs, move.delta_time, move.mouse_x, move.mouse_y)
                self.save_move(move_id, move.delta_time, move.inputs, move.mouse_x, move.mouse_y)
    
    def player_update(self, delta_time):
        if not (self.pawn and self.camera):
            return
        
        mouse = logic.mouse
        m_pos = mouse.position
        s_center = mouse.screen_center
        
        if self.mouse_setup:
            mouse_diff_x = s_center[0] - m_pos[0]
            mouse_diff_y = s_center[1] - m_pos[1]
        else:
            mouse_diff_x = mouse_diff_y = 0.0
            
            self.mouse_setup = True
        
        mouse.position = 0.5, 0.5
        
        self.execute_move(self.inputs, mouse_diff_x, mouse_diff_y, delta_time)
        self.server_validate(self.current_move_id, self.inputs, mouse_diff_x, mouse_diff_y, delta_time, self.pawn.position, self.pawn.rotation)
        self.save_move(self.current_move_id, delta_time, self.inputs.to_tuple(), mouse_diff_x, mouse_diff_y)

        self.current_move_id += 1
        if self.current_move_id == 255:
            self.current_move_id = 0
                
class Actor(Replicable):

    rigid_body_state = Attribute(RigidBodyState(), notify=True, complain=False)
    roles            = Attribute(
                          Roles(
                                Roles.authority, 
                                Roles.autonomous_proxy
                                )
                          )
        
    actor_name = ""
    actor_class = GameObject
    
    verbose_execution = True
    
    def on_initialised(self):
        super().on_initialised()
        
        self.object = self.actor_class(self.actor_name)
        self.update_simulated_physics = True
        self.camera_radius = 1
        self.always_relevant = False
    
    def on_unregistered(self):
        super().on_unregistered()

        self.object.endObject()
    
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
    
    @simulated
    def parent_to(self, obj):
        if isinstance(obj, Actor):
            obj = object.object
        self.object.setParent(obj)
    
    @simulated
    def remove_parent(self):
        self.object.removeParent()
    
    @simulated
    def suspend_physics(self):
        self.object.suspendDynamics()
    
    @simulated
    def restore_physics(self):
        self.object.restoreDynamics()
        
    @property
    def sockets(self):
        return {s['socket']: s for s in self.object.childrenRecursive if "socket" in s}
    
    @property
    def visible(self):
        return any(o.visible for o in self.object.childrenRecursive)
    
    @property
    def physics(self):
        return self.object.physicsType
    
    @property
    def has_dynamics(self):
        return self.object.physicsType in (PhysicsType.rigid_body, PhysicsType.dynamic)
    
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
    def world_position(self):
        """if not self.owner:
            return self.position
        
        else:
            owners = [self]
            owner = self.owner
            while owner:
                if isinstance(owner, Actor):
                    owners.append(actor)
                else:
                    break
                owner = owner.owner
            
            transform = Matrix.Identity(4)
            for owner in reversed(owners):
                transform = owner.transform * transform
            return transform.to_translation()"""
        return self.object.worldPosition
    @world_position.setter
    def world_position(self, pos):
        self.object.worldPosition = pos
    
    @property
    def velocity(self):
        if not self.has_dynamics:
            return Vector() 
        
        return self.object.localLinearVelocity
    @velocity.setter
    def velocity(self, vel):
        if not self.has_dynamics:
            return
        
        self.object.localLinearVelocity = vel      
          
    @property
    def angular(self):
        if not self.has_dynamics:
            return Vector()
        
        return self.object.localAngularVelocity
    @angular.setter
    def angular(self, vel):
        if not self.has_dynamics:
            return
        
        self.object.localAngularVelocity = vel

class Camera(Actor):
    
    actor_name = "Camera"
    actor_class = CameraObject        
    
    @property
    def active(self):
        return self.object == logic.getCurrentScene().active_camera
    
    @active.setter
    def active(self, status):
        if status:
            logic.getCurrentScene().active_camera = self.object
    
    @property
    def lens(self):
        return self.object.lens
    @lens.setter
    def lens(self, value):
        self.object.lens = value
    
    @property
    def fov(self):
        return self.object.fov
    @fov.setter
    def fov(self, value):
        self.object.fov = value
        
    def trace(self, x_coord, y_coord, distance=0):
        return self.object.getScreenRay(x_coord, y_coord, distance)
    
    def sees_actor(self, actor):            
        result =self.object.sphereInsideFrustum(actor.world_position, actor.camera_radius)
        render.drawLine(actor.world_position, actor.world_position + Vector((0, actor.camera_radius, 0)), [1,0,0])
        for status in "OUTSIDE", "INSIDE", "INTERSECT":
            print(result == getattr(self.object, status), status)
        
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