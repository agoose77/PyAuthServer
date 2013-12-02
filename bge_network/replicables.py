from . import bge_data
from . import structs
from . import behaviour_tree
from . import configuration
from . import enums
from . import signals
from . import inputs
from . import utilities
from . import timer
from . import draw_tools

import aud
import bge
import collections

import math
import mathutils
import network
import os
import operator
import functools

SavedMove = collections.namedtuple("Move", ("position", "rotation", "velocity", "angular",
                                "delta_time", "inputs", "mouse_x", "mouse_y"))


class Controller(network.Replicable):

    roles = network.Attribute(network.Roles(network.Roles.authority, network.Roles.autonomous_proxy))
    pawn = network.Attribute(type_of=network.Replicable, complain=True, notify=True)
    camera = network.Attribute(type_of=network.Replicable, complain=True, notify=True)
    weapon = network.Attribute(type_of=network.Replicable, complain=True, notify=True)
    info = network.Attribute(type_of=network.Replicable)

    def conditions(self, is_owner, is_complaint, is_initial):
        yield from super().conditions(is_owner, is_complaint, is_initial)

        if is_complaint:
            yield "pawn"
            yield "camera"
            yield "weapon"
            yield "info"

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
        camera.set_parent(self.pawn, "camera")

        self.camera = camera
        self.camera.possessed_by(self)

    def set_weapon(self, weapon):
        self.weapon = weapon
        self.weapon.possessed_by(self)

    def setup_weapon(self, weapon):
        self.set_weapon(weapon)
        self.pawn.weapon_attachment_class = weapon.attachment_class

    def start_server_fire(self) -> network.Netmodes.server:
        self.weapon.fire(self.camera)
        self.pawn.flash_count += 1

        for controller in network.WorldInfo.subclass_of(Controller):
            if controller == self:
                continue

            controller.hear_sound(self.weapon.shoot_sound,
                                  self.pawn.position)

    def unpossess(self):
        self.pawn.unpossessed()
        self.pawn = None


class ReplicableInfo(network.Replicable):

    def on_initialised(self):
        super().on_initialised()

        self.always_relevant = True


class PlayerReplicationInfo(ReplicableInfo):

    name = network.Attribute("")


class AIController(Controller):

    def get_visible(self, ignore_self=True):
        if not self.camera:
            return

        sees = self.camera.sees_actor

        for actor in network.WorldInfo.subclass_of(Pawn):

            if ignore_self and actor == self.pawn:
                continue

            if sees(actor):
                return actor

    def unpossess(self):
        self.behaviour.reset()
        self.behaviour.blackboard['controller'] = self
        super().unpossess()

    def hear_sound(self, sound_path, source):
        if not (self.pawn and self.camera):
            return

        probability = utilities.falloff_fraction(self.pawn.position,
                            self.hear_range,
                            source,
                            self.effective_hear)

    def on_initialised(self):
        super().on_initialised()

        self.hear_range = 15
        self.effective_hear = 10

        self.debug = False
        self.target = None

        self.camera_mode = enums.CameraMode.first_person

        self.behaviour = behaviour_tree.BehaviourTree(self)
        self.behaviour.blackboard['controller'] = self

    @network.UpdateSignal.global_listener
    def update(self, delta_time):
        self.behaviour.update(delta_time)
      #  self.behaviour.debug()


class PlayerController(Controller):

    input_fields = []

    move_error_limit = 0.15 ** 2
    config_filepath = "inputs.conf"

    @property
    def mouse_delta(self):
        '''Returns the mouse movement since the last tick'''
        mouse = bge.logic.mouse
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

    def acknowledge_good_move(self, move_id: network.StaticValue(int, max_value=1024)) -> network.Netmodes.client:
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

    def correct_bad_move(self, move_id: network.StaticValue(int, max_value=1024),
                               correction: network.StaticValue(structs.RigidBodyState)) -> network.Netmodes.client:
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
        blackboard = self.behaviour.blackboard

        blackboard['inputs'] = inputs
        blackboard['mouse'] = mouse_diff_x, mouse_diff_y

        self.behaviour.update(delta_time)

        signals.PhysicsSingleUpdateSignal.invoke(delta_time, target=self.pawn)

    def get_corrected_state(self, position, rotation):
        pos_difference = self.pawn.position - position

        if pos_difference.length_squared < self.move_error_limit:
            return

        # Create correction if neccessary
        correction = structs.RigidBodyState()

        correction.position = self.pawn.position
        correction.rotation = self.pawn.rotation
        correction.velocity = self.pawn.velocity
        correction.angular = self.pawn.angular

        return correction

    def handle_inputs(self, inputs, mouse_x, mouse_y, delta_time):
        pass

    def hear_sound(self, sound_path: network.StaticValue(str),
                   source: network.StaticValue(mathutils.Vector)) -> network.Netmodes.client:
        return
        full_path = bge.logic.expandPath('//{}'.format(sound_path))
        factory = aud.Factory.file(full_path)
        device = AudioDevice()
        # handle = device.play(factory)

    def increment_move(self):
        self.current_move_id += 1
        if self.current_move_id == 1024:
            self.current_move_id = 0

    def load_keybindings(self):
        bindings = configuration.load_configuration(self.config_filepath,
                                      self.__class__.__name__,
                                      self.input_fields)
        print("Loaded {} keybindings".format(len(bindings)))
        return bindings

    def on_initialised(self):
        super().on_initialised()

        self.setup_input()

        self.current_move_id = 0
        self.last_correction = 0
        self.previous_moves = collections.OrderedDict()

        self.mouse_setup = False
        self.camera_setup = False

        self.behaviour = behaviour_tree.BehaviourTree(self)
        self.behaviour.blackboard['controller'] = self

    @network.simulated
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

    @network.simulated
    @signals.PlayerInputSignal.global_listener
    def player_update(self, delta_time):

        if not (self.pawn and self.camera):
            return

        self.increment_move()

        # Control Mouse data
        near_zero = 0.001
        mouse_diff_x, mouse_diff_y = self.mouse_delta

        if abs(mouse_diff_x) < near_zero:
            mouse_diff_x = near_zero / 1000
        if abs(mouse_diff_y) < near_zero:
            mouse_diff_y = near_zero / 1000

#         if self.inputs.shoot:
#             self.start_fire()

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

        signals.PhysicsUnsetSimulatedSignal.invoke(target=replicable)

        self.reset_corrections(replicable)

    def receive_broadcast(self, message_string:network.StaticValue(str)) -> network.Netmodes.client:
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

    @network.RequireNetmode(network.Netmodes.client)
    def setup_input(self):
        keybindings = self.load_keybindings()

        self.inputs = inputs.InputManager(keybindings)
        print("Created input manager")

    @network.supply_data(inputs=["input_fields"])
    def server_validate(self, move_id: network.StaticValue(int, max_value=1024),
                                last_correction: network.StaticValue(int, max_value=1024),
                                inputs: network.StaticValue(inputs.InputManager),
                                mouse_diff_x: network.StaticValue(float),
                                mouse_diff_y: network.StaticValue(float),
                                delta_time: network.StaticValue(float),
                                position: network.StaticValue(mathutils.Vector),
                                rotation: network.StaticValue(mathutils.Euler)
                            ) -> network.Netmodes.server:

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
        signals.PhysicsSetSimulatedSignal.invoke(target=self.pawn)
        super().unpossess()


class Actor(network.Replicable):

    rigid_body_state = network.Attribute(structs.RigidBodyState(), notify=True)
    roles = network.Attribute(
                          network.Roles(
                                network.Roles.authority,
                                network.Roles.autonomous_proxy
                                ),
                      notify=True
                          )

    entity_name = ""
    entity_class = bge_data.GameObject

    def conditions(self, is_owner, is_complaint, is_initial):
        yield from super().conditions(is_owner, is_complaint, is_initial)

        remote_role = self.roles.remote

        # If network.simulated, send rigid body state
        if (remote_role == network.Roles.simulated_proxy) or \
            (remote_role == network.Roles.dumb_proxy) or \
            (self.roles.remote == network.Roles.autonomous_proxy and not is_owner):
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
            signals.PhysicsReplicatedSignal.invoke(self.rigid_body_state, target=self)
        else:
            super().on_notify(name)

    @signals.ActorDamagedSignal.listener
    def take_damage(self, damage, instigator, hit_position, momentum):
        self.health = int(max(self.health - damage, 0))

    @network.simulated
    def trace_ray(self, local_vector):
        target = self.transform * local_vector

        return self.object.rayCast(self.object, target)

    @network.simulated
    def align_to(self, vector, time=1, axis=enums.Axis.y):
        self.object.alignAxisToVect(vector, axis, time)

    @network.simulated
    def add_child(self, actor):
        self.children.add(actor)
        self.child_entities.add(actor.object)

    @network.simulated
    def remove_child(self, actor):
        self.children.remove(actor)
        self.child_entities.remove(actor.object)

    @network.simulated
    def set_parent(self, actor, socket_name=None):
        if socket_name is None:
            parent_obj = actor.object

        elif socket_name in actor.sockets:
            parent_obj = actor.sockets[socket_name]

        else:
            raise TypeError("Parent: {} does not have socket named {}".
                            format(actor, socket_name))

        self.object.setParent(parent_obj)
        self.parent = actor
        actor.add_child(self)

    @network.simulated
    def remove_parent(self):
        self.parent.remove_child(self)
        self.object.setParent(None)

    @network.simulated
    def restore_physics(self):
        self.object.restoreDynamics()

    @network.simulated
    def suspend_physics(self):
        self.object.suspendDynamics()

    @property
    def collision_group(self):
        return self.object.collisionGroup

    @collision_group.setter
    def collision_group(self, group):
        self.object.collisionGroup = group

    @property
    def collision_mask(self):
        return self.object.collisionMask

    @collision_mask.setter
    def collision_mask(self, mask):
        self.object.collisionMask = mask

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
        return self.object.physicsType in (enums.PhysicsType.rigid_body,
                                           enums.PhysicsType.dynamic)

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
            return mathutils.Vector()

        return self.object.localLinearVelocity

    @velocity.setter
    def velocity(self, vel):
        if not self.has_dynamics:
            return

        self.object.localLinearVelocity = vel

    @property
    def angular(self):
        if not self.has_dynamics:
            return mathutils.Vector()

        return self.object.localAngularVelocity

    @angular.setter
    def angular(self, vel):
        if not self.has_dynamics:
            return

        self.object.localAngularVelocity = vel


class Weapon(network.Replicable):
    roles = network.Attribute(network.Roles(network.Roles.authority, network.Roles.autonomous_proxy))
    ammo = network.Attribute(70)

    @property
    def can_fire(self):
        return bool(self.ammo) and \
            (network.WorldInfo.elapsed - self.last_fired_time) >= self.shoot_interval

    @property
    def sound_folder(self):
        return os.path.join(self.sound_path, self.__class__.__name__)

    @property
    def shoot_sound(self):
        return os.path.join(self.sound_folder, "shoot.wav")

    def consume_ammo(self):
        self.ammo -= 1

    def fire(self, camera):
        self.consume_ammo()

        if self.shot_type == enums.ShotType.instant:
            self.instant_shot(camera)
        else:
            self.projectile_shot()

        self.last_fired_time = network.WorldInfo.elapsed

    @network.RequireNetmode(network.Netmodes.server)
    def instant_shot(self, camera):
        hit_object, hit_position, hit_normal = camera.trace_ray(
                                                self.maximum_range)

        if not hit_object:
            return

        for replicable in network.WorldInfo.subclass_of(Actor):
            if replicable.object == hit_object:
                break
        else:
            return

        if replicable == self.owner.pawn:
            return

        hit_vector = (hit_position - camera.position)

        falloff = utilities.falloff_fraction(camera.position,
                                    self.maximum_range,
                                    hit_position, self.effective_range)

        damage = self.base_damage * falloff

        momentum = self.momentum * hit_vector.normalized() * falloff

        signals.ActorDamagedSignal.invoke(damage, self.owner, hit_position,
                                 momentum, target=replicable)

    def on_initialised(self):
        super().on_initialised()

        self.sound_path = ""
        self.shoot_interval = 0.5
        self.last_fired_time = 0.0
        self.max_ammo = 50

        self.shot_type = enums.ShotType.instant

        self.momentum = 1
        self.maximum_range = 20
        self.effective_range = 10
        self.base_damage = 40

        self.attachment_class = None


class EmptyWeapon(Weapon):

    ammo = network.Attribute(0)

    def on_initialised(self):
        super().on_initialised()

        self.attachment_class = EmptyAttatchment


class WeaponAttachment(Actor):

    roles = network.Attribute(network.Roles(network.Roles.authority, network.Roles.none))

    def on_initialised(self):
        super().on_initialised()

        self.update_simulated_physics = False

    def play_fire_effects(self):
        pass


class EmptyAttatchment(WeaponAttachment):
    entity_name = "Empty.002"


class testsignal(network.Signal):
    pass


class Camera(Actor):

    entity_class = bge_data.CameraObject
    entity_name = "Camera"

    @property
    def active(self):
        return self.object == bge.logic.getCurrentScene().active_camera

    @active.setter
    def active(self, status):
        if status:
            bge.logic.getCurrentScene().active_camera = self.object

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

    def on_initialised(self):
        super().on_initialised()

        self.mode = enums.CameraMode.third_person
        self.offset = 2.0

    def possessed_by(self, parent):
        super().possessed_by(parent)

        self.setup_camera_perspective()

    def draw(self):
        orientation = self.rotation.to_matrix() * mathutils.Matrix.Rotation(-math.radians(90),
                                                                  3, "X")

        circle_size = 0.20

        upwards_orientation = orientation * mathutils.Matrix.Rotation(math.radians(90),
                                                            3, "X")
        upwards_vector = mathutils.Vector(upwards_orientation.col[1])

        sideways_orientation = orientation * mathutils.Matrix.Rotation(math.radians(-90),
                                                             3, "Z")
        sideways_vector = (mathutils.Vector(sideways_orientation.col[1]))
        forwards_vector = mathutils.Vector(orientation.col[1])

        draw_tools.draw_arrow(self.position, orientation, colour=[0, 1, 0])
        draw_tools.draw_arrow(self.position + upwards_vector * circle_size,
                   upwards_orientation, colour=[0, 0, 1])
        draw_tools.draw_arrow(self.position + sideways_vector * circle_size,
                   sideways_orientation, colour=[1, 0, 0])
        draw_tools.draw_circle(self.position, orientation, circle_size)
        draw_tools.draw_box(self.position, orientation)
        draw_tools.draw_square_pyramid(self.position + forwards_vector * 0.4, orientation,
                            colour=[1, 1, 0], angle=self.fov, incline=False)

    def render_temporary(self, render_func):
        cam = self.object
        scene = cam.scene

        old_camera = scene.active_camera
        scene.active_camera = cam
        render_func()
        if old_camera:
            scene.active_camera = old_camera

    def setup_camera_perspective(self):
        if self.mode == enums.CameraMode.first_person:
            self.local_position = mathutils.Vector()

        else:
            self.local_position = mathutils.Vector((0, -self.offset, 0))

        self.local_rotation = mathutils.Euler((math.pi / 2, 0, 0))

    def sees_actor(self, actor):
        if not isinstance(actor, Actor):
            return False

        if actor.camera_radius < 0.5:
            return self.object.pointInsideFrustum(actor.position)

        return self.object.sphereInsideFrustum(actor.position,
                           actor.camera_radius) != self.object.OUTSIDE

    @network.simulated
    @network.UpdateSignal.global_listener
    def update(self, delta_time):
        if self.visible:
            self.draw()

    def trace(self, x_coord, y_coord, distance=0):
        return self.object.getScreenRay(x_coord, y_coord, distance)

    def trace_ray(self, distance=0):
        target = self.transform * mathutils.Vector((0, 0, -distance))
        return self.object.rayCast(target, self.position, distance)


class Pawn(Actor):

    view_pitch = network.Attribute(0.0)
    flash_count = network.Attribute(0, notify=True, complain=True)
    weapon_attachment_class = network.Attribute(type_of=network.TypeRegister,
                                        notify=True,
                                        complain=True)

    health = network.Attribute(100, notify=True, complain=True)
    alive = network.Attribute(True, notify=True, complain=True)

    def conditions(self, is_owner, is_complaint, is_initial):
        yield from super().conditions(is_owner, is_complaint, is_initial)

        if not is_owner:
            yield "view_pitch"

        if is_complaint:
            yield "weapon_attachment_class"
            yield "alive"

            if is_owner:
                yield "health"

            else:
                yield "flash_count"

    @network.simulated
    def create_weapon_attachment(self, cls):
        self.weapon_attachment = cls()
        self.weapon_attachment.set_parent(self, "weapon")

        if self.weapon_attachment is not None:
            self.weapon_attachment.unpossessed()
        self.weapon_attachment.possessed_by(self)

        self.weapon_attachment.local_position = mathutils.Vector()
        self.weapon_attachment.local_rotation = mathutils.Euler()

    def on_initialised(self):
        super().on_initialised()

        self.weapon_attachment = None
        self.navmesh_object = None

        # Non owner attributes
        self.last_flash_count = 0

        self.walk_speed = 4.0
        self.run_speed = 7.0
        self.turn_speed = 1.0

        self.animation_tolerance = 0.5

        self.animations = behaviour_tree.BehaviourTree(self)
        self.animations.blackboard['pawn'] = self

    @network.simulated
    def on_notify(self, name):
        # play weapon effects
        if name == "weapon_attachment_class":
            self.create_weapon_attachment(self.weapon_attachment_class)

        else:
            super().on_notify(name)

    def on_unregistered(self):
        if self.weapon_attachment:
            self.weapon_attachment.request_unregistration()

        super().on_unregistered()

    @network.simulated
    def play_animation(self, name, start, end, layer=0, priority=0, blend=0,
                       mode=enums.AnimationMode.play, weight=0.0, speed=1.0,
                       blend_mode=enums.AnimationBlend.interpolate):

        ge_mode = {enums.AnimationMode.play: bge.logic.KX_ACTION_MODE_PLAY,
                   enums.AnimationMode.loop: bge.logic.KX_ACTION_MODE_LOOP,
                   enums.AnimationMode.ping_pong: bge.logic.KX_ACTION_MODE_PING_PONG
                   }[mode]
        ge_blend_mode = {enums.AnimationBlend.interpolate: bge.logic.KX_ACTION_BLEND_BLEND,
                         enums.AnimationBlend.add: bge.logic.KX_ACTION_BLEND_ADD}[blend_mode]

        self.skeleton.playAction(name, start, end, layer, priority, blend,
                                 ge_mode, weight, speed=speed,
                                 blend_mode=ge_blend_mode)

    @network.simulated
    def is_playing_animation(self, layer=0):
        return self.skeleton.isPlayingAction(layer)

    @network.simulated
    def get_animation_frame(self, layer=0):
        return int(self.skeleton.getActionFrame(layer))

    @network.simulated
    def stop_animation(self, layer=0):
        self.skeleton.stopAction(layer)

    @property
    def skeleton(self):
        for child in self.object.childrenRecursive:
            if isinstance(child, bge.types.BL_ArmatureObject):
                return child

    @network.simulated
    @network.UpdateSignal.global_listener
    def update(self, delta_time):
        if self.weapon_attachment:
            self.update_weapon_attatchment()

        # Allow remote players to determine if we are alive without seeing health
        self.update_health()
        self.animations.update(delta_time)

    def update_health(self):
        '''Update health boolean
        Runs on authority / autonomous proxy only'''
        self.alive = self.health > 0

    @network.simulated
    def update_weapon_attatchment(self):
        if self.flash_count != self.last_flash_count:
            self.weapon_attachment.play_fire_effects()
            self.last_flash_count += 1

        self.weapon_attachment.local_rotation = mathutils.Euler(
                                                        (self.view_pitch, 0, 0)
                                                          )


class Navmesh(Actor):
    roles = network.Roles(network.Roles.authority, network.Roles.none)

    entity_class = bge_data.NavmeshObject
    entity_name = "Navmesh"

    def draw(self):
        self.object.draw(bge.logic.RM_TRIS)

    def find_path(self, from_point, to_point):
        return self.object.findPath(from_point, to_point)

    def get_wall_intersection(self, from_point, to_point):
        return  self.object.raycast(from_point, to_point)
