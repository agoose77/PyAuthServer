from .bge_data import RigidBodyState, GameObject, CameraObject, NavmeshObject
from .enums import PhysicsType, ShotType, CameraMode, MovementState
from .inputs import InputManager

from aud import Factory, device as AudioDevice
from bge import logic, events, render, types
from collections import namedtuple, OrderedDict
from configparser import ConfigParser, ExtendedInterpolation
from inspect import getmembers
from math import pi
from mathutils import Euler, Vector, Matrix
from network import (Replicable, Attribute, Roles, WorldInfo, 
                     simulated, Netmodes, StaticValue, run_only_on, TypeRegister)
from os import path

SavedMove = namedtuple("Move", ("position", "rotation", "velocity", "angular",
                                "delta_time", "inputs", "mouse_x", "mouse_y"))


class Controller(Replicable):

    roles = Attribute(Roles(Roles.authority, Roles.autonomous_proxy))
    pawn = Attribute(type_of=Replicable, complain=True, notify=True)
    camera = Attribute(type_of=Replicable, complain=True, notify=True)
    weapon = Attribute(type_of=Replicable, complain=True, notify=True)
    info = Attribute(type_of=Replicable)

    def conditions(self, is_owner, is_complaint, is_initial):
        yield from super().conditions(is_owner, is_complaint, is_initial)

        if is_complaint:
            yield "pawn"
            yield "camera"
            yield "weapon"
            yield "info"

    def on_initialise(self):
        self.camera_setup = False

    def on_notify(self, name):
        if name == "pawn":
            self.possess(self.pawn)

        elif name == "camera":
            self.set_camera(self.camera)
            self.camera.active = True

        elif name == "weapon":
            self.set_weapon(self.weapon)

        else:
            super().on_notify(name)

    def player_update(self, elapsed):
        pass

    def possess(self, replicable):
        self.pawn = replicable
        self.pawn.possessed_by(self)

    def receive_broadcast(self, sender: StaticValue(Replicable),
                  message_string:StaticValue(str)) -> Netmodes.client:
        print("BROADCAST: {}".format(message_string))

    def remove_camera(self):
        self.camera.unpossessed()

    def set_camera(self, camera):
        self.camera = camera
        self.camera.possessed_by(self)

    def set_weapon(self, weapon):
        self.weapon = weapon
        self.weapon.possessed_by(self)

    def unpossess(self):
        self.pawn.unpossessed()


class ReplicableInfo(Replicable):

    def on_initialised(self):
        super().on_initialised()

        self.always_relevant = True


class PlayerReplicationInfo(ReplicableInfo):

    name = Attribute("")


class PlayerController(Controller):

    input_fields = []

    move_error_limit = 0.5 ** 2
    config_filepath = "inputs.conf"

    @property
    def mouse_delta(self):
        '''Returns the mouse movement since the last tick'''
        mouse = logic.mouse
        # The first tick the mouse won't be centred
        mouse_position = mouse.position
        screen_center = mouse.screen_center

        if self.mouse_setup:
            mouse_diff_x = screen_center[0] - mouse_position[0]
            mouse_diff_y = screen_center[1] - mouse_position[1]

        else:
            mouse_diff_x = mouse_diff_y = 0.0
            self.mouse_setup = True

        mouse.position = 0.5, 0.5

        return mouse_diff_x, mouse_diff_y

    def acknowledge_good_move(self, move_id: StaticValue(int)
                              ) -> Netmodes.client:
        try:
            self.previous_moves.pop(move_id)

        except KeyError:
            print("Couldn't remove key for some reason")
            return

        additional_keys = [k for k in self.previous_moves if k < move_id]

        for key in additional_keys:
            self.previous_moves.pop(key)

    def correct_bad_move(self, move_id: StaticValue(int),
             correction: StaticValue(RigidBodyState)) -> Netmodes.client:
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
                lookup_dict.update(zip(sorted(self.inputs.keybindings),
                                       move.inputs))
                # Execute move
                self.execute_move(self.inputs, move.delta_time, move.mouse_x,
                                  move.mouse_y)
                self.save_move(move_id, move.delta_time, move.inputs,
                               move.mouse_x, move.mouse_y)

    def execute_move(self, inputs, mouse_diff_x, mouse_diff_y, delta_time):
        self.update_inputs(inputs, delta_time)
        self.update_mouse(mouse_diff_x, mouse_diff_y, delta_time)

        WorldInfo.physics.update_for(self.pawn, delta_time)

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

    def hear_sound(self, sound_path: StaticValue(str),
                   source: StaticValue(Vector)) -> Netmodes.client:
        return
        full_path = logic.expandPath('//{}'.format(sound_path))
        factory = Factory.file(full_path)
        device = AudioDevice()

        handle = device.play(factory)

    def increment_move(self):
        self.current_move_id += 1
        if self.current_move_id == 255:
            self.current_move_id = 0

    @run_only_on(Netmodes.client)
    def load_keybindings(self):
        all_events = {x[0]: str(x[1]) for x in getmembers(events)
                      if isinstance(x[1], int)}
        filepath = logic.expandPath("//" + self.config_filepath)

        # Load into parser
        parser = ConfigParser(defaults=all_events,
                              interpolation=ExtendedInterpolation())
        parser.read(filepath)

        # Read binding information
        class_name = self.__class__.type_name

        bindings = {k: int(v) for k, v in parser[class_name].items()
                if not k.upper() in all_events and k in self.input_fields}

        # Ensure we have all bindings
        assert(set(self.input_fields).issubset(bindings))

        print("Loaded {} keybindings".format(len(bindings)))
        return bindings

    def on_initialised(self):
        super().on_initialised()

        self.setup_input()

        self.current_move_id = 0
        self.previous_moves = OrderedDict()

        self.mouse_setup = False
        self.camera_setup = False

    def on_unregistered(self):
        super().on_unregistered()

        if self.pawn:
            self.pawn.request_unregistration()
            self.camera.request_unregistration()

            self.remove_camera()
            self.unpossess()

    def player_update(self, delta_time):
        if not (self.pawn and self.camera):
            return

        mouse_diff_x, mouse_diff_y = self.mouse_delta

        if self.inputs.shoot.active:
            self.start_fire()

        self.execute_move(self.inputs, mouse_diff_x, mouse_diff_y, delta_time)
        self.server_validate(self.current_move_id, self.inputs, mouse_diff_x,
                             mouse_diff_y, delta_time, self.pawn.position,
                             self.pawn.rotation)

        self.save_move(self.current_move_id, delta_time,
                       self.inputs.to_tuple(), mouse_diff_x,
                       mouse_diff_y)

        self.increment_move()

    def possess(self, replicable):
        WorldInfo.physics.add_exemption(replicable)

        super().possess(replicable)

    def save_move(self, move_id, delta_time, input_tuple, mouse_diff_x,
                  mouse_diff_y):
        self.previous_moves[move_id] = SavedMove(self.pawn.position.copy(),
                                                 self.pawn.rotation.copy(),
                                                  self.pawn.velocity.copy(),
                                                  self.pawn.angular.copy(),
                                                  delta_time, input_tuple,
                                                  mouse_diff_x, mouse_diff_y)

    @run_only_on(Netmodes.client)
    def setup_input(self):
        keybindings = self.load_keybindings()

        self.inputs = InputManager(keybindings)
        print("Created input manager")

    def server_validate(self, move_id:StaticValue(int),
                            inputs: StaticValue(InputManager,
                                        class_data={"fields": "input_fields"}),
                            mouse_diff_x: StaticValue(float),
                            mouse_diff_y: StaticValue(float),
                            delta_time: StaticValue(float),
                            position: StaticValue(Vector),
                            rotation: StaticValue(Euler)
                        ) -> Netmodes.server:
        print("QWDS")
        self.current_move_id = move_id

        self.execute_move(inputs, mouse_diff_x, mouse_diff_y, delta_time)

        self.save_move(move_id, delta_time, inputs.to_tuple(), mouse_diff_x,
                       mouse_diff_y)

        correction = self.get_corrected_state(position, rotation)

        if correction is None:
            self.acknowledge_good_move(self.current_move_id)

        else:
            self.correct_bad_move(self.current_move_id, correction)

    def set_camera(self, camera):
        super().set_camera(camera)

        camera_socket = self.pawn.sockets['camera']
        camera.parent_to(camera_socket)

        self.setup_camera_perspective(camera)

    def setup_camera_perspective(self, camera):
        if camera.look_mode == CameraMode.first_person:
            camera.position = Vector()

        else:
            camera.position = Vector((0, -camera.third_person_offset, 0))

        camera.rotation = Euler((pi / 2, 0, 0))

    def setup_weapon(self, weapon):
        super().set_weapon(weapon)

        self.pawn.weapon_attachment_class = weapon.attachment_class

    def start_fire(self):
        if not self.weapon:
            return

        self.start_server_fire()
        self.start_client_fire()

    def start_client_fire(self):
        if not self.weapon.can_fire or not self.camera:
            return

        self.weapon.fire(self.camera)

        self.pawn.weapon_attachment.play_fire_effects()
        self.hear_sound(self.weapon.shoot_sound, self.pawn.position)

    def start_server_fire(self) -> Netmodes.server:
        if not self.weapon.can_fire or not self.camera:
            return

        self.weapon.fire(self.camera)

        for controller in WorldInfo.subclass_of(PlayerController):
            if controller == self:
                continue

            controller.hear_sound(self.weapon.shoot_sound,
                                  self.pawn.world_position)

    def unpossess(self):
        WorldInfo.physics.remove_exemption(self.pawn)

        super().unpossess()

    def update_inputs(self, inputs, delta_time):
        pass

    def update_mouse(self, mouse_x, mouse_y, delta_time):
        pass


class Actor(Replicable):

    rigid_body_state = Attribute(RigidBodyState(), notify=True, complain=False)
    roles = Attribute(
                          Roles(
                                Roles.authority,
                                Roles.autonomous_proxy
                                )
                          )

    health = Attribute(100.0, notify=True)

    entity_name = ""
    actor_class = GameObject

    verbose_execution = True

    def conditions(self, is_owner, is_complaint, is_initial):
        yield from super().conditions(is_owner, is_complaint, is_initial)

        remote_role = self.roles.remote

        if is_complaint and (is_owner):
            yield "health"

        # If simulated, send rigid body state
        if (remote_role == Roles.simulated_proxy) or \
            (remote_role == Roles.dumb_proxy) or \
            (self.roles.remote == Roles.autonomous_proxy and not is_owner):

            if self.update_simulated_physics or is_initial:
                yield "rigid_body_state"

    def on_initialised(self):
        super().on_initialised()

        self.object = self.actor_class(self.entity_name)
        self.update_simulated_physics = True
        self.always_relevant = False
        self.camera_radius = 1

    def on_unregistered(self):
        super().on_unregistered()
        self.object.endObject()

    def on_notify(self, name):
        if name == "rigid_body_state":
            WorldInfo.physics.actor_replicated(self, self.rigid_body_state)

        else:
            super().on_notify(name)

    def take_damage(self, damage, instigator, hit_position, momentum):
        print("Take damage")
        self.health = max(self.health - damage, 0)

    @simulated
    def on_collision(self, actor, new_collision):
        print(actor, new_collision)

    @simulated
    def parent_to(self, obj):
        if isinstance(obj, Actor):
            obj = object.object

        self.object.setParent(obj)

    @simulated
    def play_animation(self, name, start, end, layer=0, priority=0, blend=0,
                       mode=logic.KX_ACTION_MODE_PLAY, weight=0.0, speed=1.0,
                       blend_mode=logic.KX_ACTION_BLEND_BLEND):

        self.skeleton.playAction(name, start, end, layer, priority, blend,
                                 mode, weight, speed=speed,
                                 blend_mode=blend_mode)

    @simulated
    def playing_animation(self, layer=0):
        return self.skeleton.isPlayingAction(layer)

    @simulated
    def stop_animation(self, layer=0):
        self.skeleton.stopAction(layer)

    @simulated
    def remove_parent(self):
        self.object.removeParent()

    @simulated
    def restore_physics(self):
        self.object.restoreDynamics()

    @simulated
    def suspend_physics(self):
        self.object.suspendDynamics()

    @property
    def skeleton(self):
        for c in self.object.childrenRecursive:
            if isinstance(c, types.BL_ArmatureObject):
                return c

    @property
    def visible(self):
        return any(o.visible for o in self.object.childrenRecursive)

    @property
    def physics(self):
        return self.object.physicsType

    @property
    def sockets(self):
        return {s['socket']: s for s in self.object.childrenRecursive
                if "socket" in s}

    @property
    def has_dynamics(self):
        return self.object.physicsType in (PhysicsType.rigid_body,
                                           PhysicsType.dynamic)

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
        return self.object.worldPosition

    @world_position.setter
    def world_position(self, pos):
        self.object.worldPosition = pos

    @property
    def world_rotation(self):
        return self.object.worldOrientation.to_euler()

    @world_rotation.setter
    def world_rotation(self, ori):
        self.object.worldOrientation = ori

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


class Weapon(Replicable):
    roles = Attribute(Roles(Roles.authority, Roles.autonomous_proxy))
    ammo = Attribute(7)

    def on_initialised(self):
        super().on_initialised()

        self.sound_path = ""
        self.shoot_interval = 0.5
        self.last_fired_time = 0.0
        self.max_ammo = 50
        self.range = 20
        self.shot_type = ShotType.instant

        self.momentum = 1
        self.maximum_range = 20
        self.effective_range = 10
        self.base_damage = 40

        self.attachment_class = WeaponAttachment

    @property
    def can_fire(self):
        return bool(self.ammo) and \
            (WorldInfo.elapsed - self.last_fired_time) >= self.shoot_interval

    def consume_ammo(self):
        self.ammo -= 1

    def fire(self, camera):
        self.consume_ammo()

        if self.shot_type == ShotType.instant:
            self.instant_shot(camera)
        else:
            self.projectile_shot()

        self.last_fired_time = WorldInfo.elapsed

    @run_only_on(Netmodes.server)
    def instant_shot(self, camera):
        hit_object, hit_position, hit_normal = camera.trace_ray(
                                                self.maximum_range)

        camera.draw_from_center()

        if not hit_object:
            return

        for replicable in WorldInfo.subclass_of(Actor):
            if replicable.object == hit_object:
                break
        else:
            return

        hit_vector = (camera.world_position - hit_position)
        distance = hit_vector.length

        # If in optimal range
        if distance <= self.effective_range:
            falloff = 1

        # If we are beyond optimal range
        else:
            distance_fraction = (((distance - self.effective_range) ** 2)
                         / (self.maximum_range - self.effective_range) ** 2)
            falloff = (1 - distance_fraction)

        damage = self.base_damage * falloff

        momentum = self.momentum * hit_vector.normalized() * falloff

        replicable.take_damage(damage, self.owner, hit_position, momentum)

    @property
    def sound_folder(self):
        return path.join(self.sound_path, self.__class__.__name__)

    @property
    def shoot_sound(self):
        return path.join(self.sound_folder, "shoot.wav")


class WeaponAttachment(Actor):

    roles = Attribute(Roles(Roles.authority, Roles.none))

    def play_fire_effects(self):
        pass


class Camera(Actor):

    entity_name = "Camera"
    actor_class = CameraObject

    @property
    def visible(self):
        return False

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

    def draw_from_center(self, length=2, colour=[1, 0, 1]):
        source = self.world_position
        rotation = self.object.worldOrientation
        target = source + rotation * Vector((0, 0, -length))
        render.drawLine(source, target, colour)

    def on_initialised(self):
        super().on_initialised()

        self.look_mode = CameraMode.third_person
        self.third_person_offset = 2.0

    def render_temporary(self, render_func):
        cam = self.object
        scene = cam.scene

        old_camera = scene.active_camera
        scene.active_camera = cam
        render_func()
        scene.active_camera = old_camera

    def sees_actor(self, replicable):
        if replicable.camera_radius < 0.5:
            return self.object.pointInsideFrustum(replicable.world_position)

        return self.object.sphereInsideFrustum(replicable.world_position,
                           replicable.camera_radius) != self.object.OUTSIDE

    def trace(self, x_coord, y_coord, distance=0):
        return self.object.getScreenRay(x_coord, y_coord, distance)

    def trace_ray(self, distance=0):
        target = Vector((0, distance, 0))
        target.rotate(Euler((pi / 2, 0, 0)))
        target.rotate(self.world_rotation)
        return self.object.rayCast(target, self.world_position, distance)


class Pawn(Actor):

    view_pitch = Attribute(0.0)
    flash_count = Attribute(0,
                   notify=True,
                        complain=False)

    weapon_attachment_class = Attribute(type_of=TypeRegister,
                                        notify=True,
                                        pointer_type=WeaponAttachment)

    @property
    def movement_state(self):
        movement_speed = self.velocity.xy.length

        if movement_speed < self.animation_tolerance:
            state = MovementState.static

        elif abs(self.walk_speed - movement_speed) < self.animation_tolerance:
            state = MovementState.walk

        elif abs(self.run_speed - movement_speed) < self.animation_tolerance:
            state = MovementState.run

        else:
            state = MovementState.static

        return state

    def conditions(self, is_owner, is_complaint, is_initial):
        yield from super().conditions(is_owner, is_complaint, is_initial)

        if not is_owner:
            yield "flash_count"
            yield "view_pitch"

        if is_complaint:
            yield "weapon_attachment_class"

    def create_weapon_attachment(self, cls):
        self.weapon_attachment = cls()
        self.weapon_attachment.parent_to(self.sockets['weapon'])

        self.weapon_attachment.position = Vector()
        self.weapon_attachment.rotation = Euler()

    def handle_animation(self, movement_mode):
        pass

    def on_initialised(self):
        super().on_initialised()

        self.weapon_attachment = None

        # Non owner attributes
        self.last_flash_count = 0
        self.outstanding_flash = 0

        self.walk_speed = 4.0
        self.run_speed = 7.0

        self.animation_tolerance = 0.5

    def on_notify(self, name):

        # play weapon effects
        if name == "flash_count":
            self.update_flashcount()

        elif name == "weapon_attachment_class":
            self.create_weapon_attachment(self.weapon_attachment_class)

        else:
            super().on_notify(name)

    def on_unregistered(self):
        super().on_unregistered()

        if self.weapon_attachment:
            self.weapon_attachment.request_unregistration()

    @simulated
    def update(self, delta_time):
        if self.outstanding_flash:
            self.use_flashcount()

        if self.weapon_attachment:
            self.weapon_attachment.rotation = Euler((self.view_pitch, 0, 0))

        self.handle_animation(self.movement_state)

    @simulated
    def update_flashcout(self):
        self.outstanding_flash += self.flash_count - self.last_flash_count
        self.last_flash_count = self.flash_count

    @simulated
    def use_flashcout(self):
        self.weapon_attachment.play_firing_effects()
        self.outstanding_flash -= 1


class Navmesh(Actor):
    roles = Roles(Roles.authority, Roles.none)

    actor_class = NavmeshObject

    def get_wall_intersection(self, from_point, to_point):
        return  self.object.raycast(from_point, to_point)

    def draw(self):
        self.object.draw()

    def find_path(self, from_point, to_point):
        return self.object.findPath(from_point, to_point)
