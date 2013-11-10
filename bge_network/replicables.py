from .bge_data import RigidBodyState, GameObject, CameraObject, NavmeshObject
from .behaviour_tree import BehaviourTree
from .configuration import load_configuration
from .enums import (PhysicsType, ShotType, CameraMode, AIState,
                    Axis)
from .signals import (CollisionSignal, PlayerInputSignal,
                    PhysicsReplicatedSignal, PhysicsSingleUpdateSignal,
                    PhysicsSetSimulatedSignal, PhysicsUnsetSimulatedSignal,
                    ActorDamagedSignal, ActorKilledSignal, SetMoveTarget)
from .inputs import InputManager
from .utilities import falloff_fraction, progress_string
from .timer import ManualTimer
from .draw_tools import (draw_arrow, draw_circle,
                         draw_box, draw_square_pyramid)

from aud import Factory, device as AudioDevice
from bge import logic, types
from collections import namedtuple, OrderedDict

from math import pi, radians
from mathutils import Euler, Vector, Matrix
from network import (Replicable, Attribute, Roles, WorldInfo,
                     simulated, Netmodes, StaticValue, run_on, TypeRegister,
                     ReplicableUnregisteredSignal, UpdateSignal, ConnectionInterface,
                     ConnectionStatus)
from os import path
from operator import gt as more_than
from functools import lru_cache

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

    def hear_sound(self, path, location):
        pass

    @ActorDamagedSignal.listener
    def on_damaged(self, damage, instigator, hit_position, momentum):
        pass

    def on_initialised(self):
        self.camera_setup = False
        self.camera_mode = CameraMode.third_person
        self.camera_offset = 2.0

        super().on_initialised()

    def on_unregistered(self):
        if self.pawn:
            self.pawn.request_unregistration()
            self.camera.request_unregistration()

            self.remove_camera()
            self.unpossess()

        super().on_unregistered()

    def possess(self, replicable):
        self.pawn = replicable
        self.pawn.possessed_by(self)

        replicable.register_child(self)

    def remove_camera(self):
        self.camera.unpossessed()

    def set_camera(self, camera):
        self.camera = camera
        self.camera.possessed_by(self)

        camera.set_parent(self.pawn, "camera")

        self.setup_camera_perspective(camera)

    def set_weapon(self, weapon):
        self.weapon = weapon
        self.weapon.possessed_by(self)

    def setup_camera_perspective(self, camera):
        if self.camera_mode == CameraMode.first_person:
            camera.local_position = Vector()

        else:
            camera.local_position = Vector((0, -self.camera_offset, 0))

        camera.local_rotation = Euler((pi / 2, 0, 0))

    def setup_weapon(self, weapon):
        self.set_weapon(weapon)

        self.pawn.weapon_attachment_class = weapon.attachment_class

    def start_server_fire(self) -> Netmodes.server:

        if not self.weapon.can_fire:
            return
        self.weapon.fire(self.camera)

        for controller in WorldInfo.subclass_of(Controller):
            if controller == self:
                continue

            controller.hear_sound(self.weapon.shoot_sound,
                                  self.pawn.position)

    def unpossess(self):
        self.pawn.unpossessed()
        self.pawn = None


class ReplicableInfo(Replicable):

    def on_initialised(self):
        super().on_initialised()

        self.always_relevant = True


class PlayerReplicationInfo(ReplicableInfo):

    name = Attribute("")


class AIController(Controller):

    def get_visible(self, ignore_self=True):
        if not self.camera:
            return

        sees = self.camera.sees_actor

        for actor in WorldInfo.subclass_of(Pawn):

            if ignore_self and actor == self.pawn:
                continue

            if sees(actor):
                return actor

    def hear_sound(self, path, source):
        if not (self.pawn and self.camera):
            return

        probability = falloff_fraction(self.pawn.position,
                            self.hear_range,
                            source,
                            self.effective_hear)

    def on_initialised(self):
        super().on_initialised()

        self.hear_range = 15
        self.effective_hear = 10

        self.target_dir = None
        self.target = None

        self.camera_mode = CameraMode.first_person

        self.animations = BehaviourTree(self)
        self.animations.blackboard['controller'] = self

    @UpdateSignal.global_listener
    def update(self, delta_time):
        self.animations.update(delta_time)


class PlayerController(Controller):

    input_fields = []

    move_error_limit = 0.15 ** 2
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

    def acknowledge_good_move(self, move_id: StaticValue(int, max_value=1024)) -> Netmodes.client:
        self.last_correction = move_id

        try:
            self.previous_moves.pop(move_id)

        except KeyError:
            print("Couldn't find move to acknowledge for move {}".format(move_id))
            return

        additional_keys = [k for k in self.previous_moves if k < move_id]

        for key in additional_keys:
            self.previous_moves.pop(key)

        return True

    def correct_bad_move(self, move_id: StaticValue(int, max_value=1024),
                               correction: StaticValue(RigidBodyState)) -> Netmodes.client:
        if not self.acknowledge_good_move(move_id):
            print("No move found")
            return

        self.pawn.position = correction.position
        self.pawn.velocity = correction.velocity
        self.pawn.rotation = correction.rotation
        self.pawn.angular = correction.angular

        lookup_dict = {}

        print("{}: Correcting prediction for move {}".format(self, move_id))

        with self.inputs.using_interface(lookup_dict.__getitem__):

            for ind, (move_id, move) in enumerate(self.previous_moves.items()):
                # Restore inputs
                inputs_dict = dict(zip(sorted(self.inputs.keybindings),
                                       move.inputs))
                lookup_dict.update(inputs_dict)
                # Execute move
                self.execute_move(self.inputs, move.mouse_x,
                                  move.mouse_y, move.delta_time)
                self.save_move(move_id, move.delta_time, move.inputs,
                               move.mouse_x, move.mouse_y)

    def execute_move(self, inputs, mouse_diff_x, mouse_diff_y, delta_time):
        self.handle_inputs(inputs, mouse_diff_x, mouse_diff_y, delta_time)
        PhysicsSingleUpdateSignal.invoke(delta_time, target=self.pawn)

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

    def handle_inputs(self, inputs, mouse_x, mouse_y, delta_time):
        pass

    def hear_sound(self, sound_path: StaticValue(str),
                   source: StaticValue(Vector)) -> Netmodes.client:
        return
        full_path = logic.expandPath('//{}'.format(sound_path))
        factory = Factory.file(full_path)
        device = AudioDevice()
        # handle = device.play(factory)

    def increment_move(self):
        self.current_move_id += 1
        if self.current_move_id == 1024:
            self.current_move_id = 0

    def load_keybindings(self):
        bindings = load_configuration(self.config_filepath,
                                      self.__class__.__name__,
                                      self.input_fields)
        print("Loaded {} keybindings".format(len(bindings)))
        return bindings

    def on_initialised(self):
        super().on_initialised()

        self.setup_input()

        self.current_move_id = 0
        self.last_correction = 0
        self.previous_moves = OrderedDict()

        self.mouse_setup = False
        self.camera_setup = False

    @simulated
    def on_notify(self, name):
        if name == "pawn":
            if self.pawn:
                self.possess(self.pawn)
            else:
                self.unpossess()

        elif name == "camera":
            self.set_camera(self.camera)
            self.camera.active = True

        elif name == "weapon":
            self.set_weapon(self.weapon)

        else:
            super().on_notify(name)

    @simulated
    @PlayerInputSignal.global_listener
    def player_update(self, delta_time):

        if not (self.pawn and self.camera):
            return
        self.normal_update(delta_time)

    def debug_update(self, delta_time):
        if self.inputs.shoot:
            self.increment_move()

            mouse_diff_x, mouse_diff_y = self.mouse_delta

            self.execute_move(self.inputs, mouse_diff_x, mouse_diff_y, delta_time)

            self.save_move(self.current_move_id, delta_time,
                           self.inputs.to_tuple(), mouse_diff_x,
                           mouse_diff_y)

        elif self.inputs.run:
            move_id = min(self.previous_moves)
            self.correct_bad_move(move_id, self.previous_moves[move_id])

    def normal_update(self, delta_time):
        self.increment_move()

        mouse_diff_x, mouse_diff_y = self.mouse_delta

        if self.inputs.shoot:
            self.start_fire()

        self.execute_move(self.inputs, mouse_diff_x, mouse_diff_y, delta_time)

        self.save_move(self.current_move_id, delta_time,
                       self.inputs.to_tuple(), mouse_diff_x,
                       mouse_diff_y)

        self.server_validate(self.current_move_id,
                             self.last_correction,
                             self.inputs, mouse_diff_x,
                             mouse_diff_y, delta_time, self.pawn.position,
                             self.pawn.rotation)

    def possess(self, replicable):
        super().possess(replicable)

        PhysicsUnsetSimulatedSignal.invoke(target=replicable)

        self.reset_corrections(replicable)

    def receive_broadcast(self, message_string:StaticValue(str)) -> Netmodes.client:
        print("BROADCAST: {}".format(message_string))

    def reset_corrections(self, replicable):
        '''Forces the client to be corrected when spawned'''
        self.last_correction = 0

    def save_move(self, move_id, delta_time, input_tuple, mouse_diff_x,
                  mouse_diff_y):
        self.previous_moves[move_id] = SavedMove(self.pawn.position.copy(),
                                                 self.pawn.rotation.copy(),
                                                  self.pawn.velocity.copy(),
                                                  self.pawn.angular.copy(),
                                                  delta_time, input_tuple,
                                                  mouse_diff_x, mouse_diff_y)

    @run_on(Netmodes.client)
    def setup_input(self):
        keybindings = self.load_keybindings()

        self.inputs = InputManager(keybindings)
        print("Created input manager")

    def server_validate(self, move_id: StaticValue(int, max_value=1024),
                                last_correction: StaticValue(int, max_value=1024),
                                inputs: StaticValue(InputManager,
                                            class_data={"fields":
                                                        "input_fields"}),
                                mouse_diff_x: StaticValue(float),
                                mouse_diff_y: StaticValue(float),
                                delta_time: StaticValue(float),
                                position: StaticValue(Vector),
                                rotation: StaticValue(Euler)
                            ) -> Netmodes.server:

        if not (self.pawn and self.camera):
            return

        self.current_move_id = move_id

        self.execute_move(inputs, mouse_diff_x, mouse_diff_y, delta_time)

        self.save_move(move_id, delta_time, inputs.to_tuple(), mouse_diff_x,
                       mouse_diff_y)

        correction = self.get_corrected_state(position, rotation)

        if correction is None or (last_correction < self.last_correction):
            self.acknowledge_good_move(move_id)

        else:
            self.correct_bad_move(move_id, correction)
            self.last_correction = move_id

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

    def unpossess(self):
        PhysicsSetSimulatedSignal.invoke(target=self.pawn)
        super().unpossess()


class Actor(Replicable):

    rigid_body_state = Attribute(RigidBodyState(), notify=True, complain=False)
    roles = Attribute(
                          Roles(
                                Roles.authority,
                                Roles.autonomous_proxy
                                )
                          )

    health = Attribute(100, notify=True)

    entity_name = ""
    entity_class = GameObject

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

        self.object = self.entity_class(self.entity_name)
        self.camera_radius = 1

        self.update_simulated_physics = True
        self.always_relevant = False

        self.children = set()
        self.parent = None

        self.child_entities = set()

    def on_unregistered(self):

        # Unregister any actor children
        for child in self.children:
            child.request_unregistration()

        # Unregister from parent
        if self.parent:
            self.parent.remove_child(self)

        self.children.clear()
        self.child_entities.clear()
        self.object.endObject()

        super().on_unregistered()

    def on_notify(self, name):
        if name == "rigid_body_state":
            PhysicsReplicatedSignal.invoke(self.rigid_body_state, target=self)
        else:
            super().on_notify(name)

    @ActorDamagedSignal.listener
    def take_damage(self, damage, instigator, hit_position, momentum):
        self.health = int(max(self.health - damage, 0))

    @simulated
    def trace_ray(self, local_vector):
        target = self.transform * local_vector

        return self.object.rayCast(self.object, target)

    @simulated
    def align_to(self, vector, time=1, axis=Axis.y):
        self.object.alignAxisToVect(vector, axis, time)

    @simulated
    def add_child(self, actor):
        self.children.add(actor)
        self.child_entities.add(actor.object)

    @simulated
    def remove_child(self, actor):
        self.children.remove(actor)
        self.child_entities.remove(actor.object)

    @simulated
    def set_parent(self, actor, socket_name=None):
        if socket_name is None:
            parent_obj = actor.object

        elif socket_name in actor.sockets:
            parent_obj = actor.sockets[socket_name]

        else:
            print(actor.sockets, actor.object)
            raise TypeError("Parent: {} does not have socket named {}".
                            format(actor, socket_name))

        self.object.setParent(parent_obj)
        self.parent = actor
        actor.add_child(self)

    @simulated
    def remove_parent(self):
        self.parent.remove_child(self)
        self.object.setParent(None)

    @simulated
    def play_animation(self, name, start, end, layer=0, priority=0, blend=0,
                       mode=logic.KX_ACTION_MODE_PLAY, weight=0.0, speed=1.0,
                       blend_mode=logic.KX_ACTION_BLEND_BLEND):

        self.skeleton.playAction(name, start, end, layer, priority, blend,
                                 mode, weight, speed=speed,
                                 blend_mode=blend_mode)

    @simulated
    def is_playing_animation(self, layer=0):
        return self.skeleton.isPlayingAction(layer)

    @simulated
    def get_animation_frame(self, layer=0):
        return self.skeleton.getActionFrame(layer)

    @simulated
    def stop_animation(self, layer=0):
        self.skeleton.stopAction(layer)

    @simulated
    def restore_physics(self):
        self.object.restoreDynamics()

    @simulated
    def suspend_physics(self):
        self.object.suspendDynamics()

    @property
    def skeleton(self):
        for child in self.object.childrenRecursive:
            if isinstance(child, types.BL_ArmatureObject):
                return child

    @property
    def visible(self):
        return any(o.visible and o.meshes
                   for o in self.object.childrenRecursive)

    @property
    def physics(self):
        return self.object.physicsType

    @property
    def sockets(self):
        return {s['socket']: s for s in
                self.object.childrenRecursive if "socket" in s}

    @property
    def has_dynamics(self):
        return self.object.physicsType in (PhysicsType.rigid_body,
                                           PhysicsType.dynamic)

    @property
    def transform(self):
        return self.object.worldTransform

    @transform.setter
    def transform(self, val):
        self.object.worldTransform = val

    @property
    def rotation(self):
        return self.object.worldOrientation.to_euler()

    @rotation.setter
    def rotation(self, rot):
        self.object.worldOrientation = rot

    @property
    def position(self):
        return self.object.worldPosition

    @position.setter
    def position(self, pos):
        self.object.worldPosition = pos

    @property
    def local_position(self):
        return self.object.localPosition

    @local_position.setter
    def local_position(self, pos):
        self.object.localPosition = pos

    @property
    def local_rotation(self):
        return self.object.localOrientation.to_euler()

    @local_rotation.setter
    def local_rotation(self, ori):
        self.object.localOrientation = ori

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
    ammo = Attribute(70)

    @property
    def can_fire(self):
        return bool(self.ammo) and \
            (WorldInfo.elapsed - self.last_fired_time) >= self.shoot_interval

    @property
    def sound_folder(self):
        return path.join(self.sound_path, self.__class__.__name__)

    @property
    def shoot_sound(self):
        return path.join(self.sound_folder, "shoot.wav")

    def consume_ammo(self):
        self.ammo -= 1

    def fire(self, camera):
        self.consume_ammo()

        if self.shot_type == ShotType.instant:
            self.instant_shot(camera)
        else:
            self.projectile_shot()

        self.last_fired_time = WorldInfo.elapsed

    @run_on(Netmodes.server)
    def instant_shot(self, camera):
        hit_object, hit_position, hit_normal = camera.trace_ray(
                                                self.maximum_range)

        if not hit_object:
            return

        for replicable in WorldInfo.subclass_of(Actor):
            if replicable.object == hit_object:
                break
        else:
            return

        if replicable == self.owner.pawn:
            return

        hit_vector = (hit_position - camera.position)

        falloff = falloff_fraction(camera.position,
                                    self.maximum_range,
                                    hit_position, self.effective_range)

        damage = self.base_damage * falloff

        momentum = self.momentum * hit_vector.normalized() * falloff

        ActorDamagedSignal.invoke(damage, self.owner, hit_position,
                                 momentum, target=replicable)

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


class EmptyWeapon(Weapon):

    ammo = Attribute(0)

    def on_initialised(self):
        super().on_initialised()

        self.attachment_class = EmptyAttatchment


class WeaponAttachment(Actor):

    roles = Attribute(Roles(Roles.authority, Roles.none))

    def on_initialised(self):
        super().on_initialised()

        self.update_simulated_physics = False

    def play_fire_effects(self):
        pass


class EmptyAttatchment(WeaponAttachment):
    entity_name = "Empty.002"


class Camera(Actor):

    entity_class = CameraObject
    entity_name = "Camera"

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

    def draw(self):
        orientation = self.rotation.to_matrix() * Matrix.Rotation(-radians(90),
                                                                  3, "X")

        circle_size = 0.20

        upwards_orientation = orientation * Matrix.Rotation(radians(90),
                                                            3, "X")
        upwards_vector = Vector(upwards_orientation.col[1])

        sideways_orientation = orientation * Matrix.Rotation(radians(-90),
                                                             3, "Z")
        sideways_vector = (Vector(sideways_orientation.col[1]))
        forwards_vector = Vector(orientation.col[1])

        draw_arrow(self.position, orientation, colour=[0, 1, 0])
        draw_arrow(self.position + upwards_vector * circle_size,
                   upwards_orientation, colour=[0, 0, 1])
        draw_arrow(self.position + sideways_vector * circle_size,
                   sideways_orientation, colour=[1, 0, 0])
        draw_circle(self.position, orientation, circle_size)
        draw_box(self.position, orientation)
        draw_square_pyramid(self.position + forwards_vector * 0.4, orientation,
                            colour=[1, 1, 0], angle=self.fov, incline=False)

    def render_temporary(self, render_func):
        cam = self.object
        scene = cam.scene

        old_camera = scene.active_camera
        scene.active_camera = cam
        render_func()
        if old_camera:
            scene.active_camera = old_camera

    def sees_actor(self, actor):
        if not isinstance(actor, Actor):
            return False

        if actor.camera_radius < 0.5:
            return self.object.pointInsideFrustum(actor.position)

        return self.object.sphereInsideFrustum(actor.position,
                           actor.camera_radius) != self.object.OUTSIDE

    @simulated
    @UpdateSignal.global_listener
    def update(self, delta_time):
        if self.visible:
            self.draw()

    def trace(self, x_coord, y_coord, distance=0):
        return self.object.getScreenRay(x_coord, y_coord, distance)

    def trace_ray(self, distance=0):
        target = self.transform * Vector((0, 0, -distance))
        return self.object.rayCast(target, self.position, distance)


class Pawn(Actor):

    view_pitch = Attribute(0.0)
    flash_count = Attribute(0,
                   notify=True,
                        complain=False)
    weapon_attachment_class = Attribute(type_of=TypeRegister,
                                        notify=True)

    def conditions(self, is_owner, is_complaint, is_initial):
        yield from super().conditions(is_owner, is_complaint, is_initial)

        if not is_owner:
            yield "flash_count"
            yield "view_pitch"

        if is_complaint:
            yield "weapon_attachment_class"

    def create_weapon_attachment(self, cls):
        self.weapon_attachment = cls()
        self.weapon_attachment.set_parent(self, "weapon")

        self.weapon_attachment.local_position = Vector()
        self.weapon_attachment.local_rotation = Euler()

    def on_initialised(self):
        super().on_initialised()

        self.weapon_attachment = None
        self.navmesh_object = None

        # Non owner attributes
        self.last_flash_count = 0
        self.outstanding_flash = 0

        self.walk_speed = 4.0
        self.run_speed = 7.0
        self.turn_speed = 1.0

        self.animation_tolerance = 0.5

        self.animations = BehaviourTree(self)
        self.animations.blackboard['pawn'] = self

        self.target = None

    def on_notify(self, name):

        # play weapon effects
        if name == "flash_count":
            self.update_flashcount()

        elif name == "weapon_attachment_class":
            self.create_weapon_attachment(self.weapon_attachment_class)

        else:
            super().on_notify(name)

    def on_unregistered(self):
        if self.weapon_attachment:
            self.weapon_attachment.request_unregistration()

        super().on_unregistered()

    @simulated
    @SetMoveTarget.listener
    def track_toward(self, actor):
        self.target = actor

    @simulated
    @UpdateSignal.global_listener
    def update(self, delta_time):
        if self.outstanding_flash:
            self.use_flashcount()

        if self.weapon_attachment:
            self.weapon_attachment.local_rotation = Euler((self.view_pitch, 0,
                                                           0))

    @simulated
    def update_flashcount(self):
        self.outstanding_flash += self.flash_count - self.last_flash_count
        self.last_flash_count = self.flash_count

    @simulated
    def use_flashcout(self):
        self.weapon_attachment.play_firing_effects()
        self.outstanding_flash -= 1

    @simulated
    @UpdateSignal.global_listener
    def update(self, delta_time):
        self.animations.update(delta_time)


class Navmesh(Actor):
    roles = Roles(Roles.authority, Roles.none)

    entity_class = NavmeshObject
    entity_name = "Navmesh"

    def draw(self):
        self.object.draw()

    def find_path(self, from_point, to_point):
        return self.object.findPath(from_point, to_point)

    def get_wall_intersection(self, from_point, to_point):
        return  self.object.raycast(from_point, to_point)
