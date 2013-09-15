from .bge_data import RigidBodyState, GameObject, CameraObject, NavmeshObject
from .events import CollisionEvent, PlayerInputEvent, UpdateEvent, PhysicsReplicatedEvent, PhysicsSingleUpdate, PhysicsSetSimulated, PhysicsUnsetSimulated
from .enums import PhysicsType, ShotType, CameraMode, MovementState, AIState, Axis
from .inputs import InputManager
from .utilities import falloff_fraction, clamp
from .finite_state_machine import FiniteStateMachine
from .timer import Timer
from .draw_tools import draw_arrow, draw_circle, draw_box, draw_square_pyramid, draw_plane

from aud import Factory, device as AudioDevice
from bge import logic, events, render, types
from collections import namedtuple, OrderedDict
from configparser import ConfigParser, ExtendedInterpolation
from inspect import getmembers
from functools import partial
from math import pi, radians
from mathutils import Euler, Vector, Matrix
from network import (Replicable, Attribute, Roles, WorldInfo,
                     simulated, Netmodes, StaticValue, run_on, TypeRegister,
                     event, ReplicableInstantiatedEvent,
                     ReplicableRegisteredEvent, ReplicableUnregisteredEvent)
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

    @event(ReplicableInstantiatedEvent)
    def on_initialised(self):
        self.camera_setup = False
        self.camera_mode = CameraMode.third_person
        self.camera_offset = 2.0

        self.state_manager = FiniteStateMachine()

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

    def on_damaged(self, damage, instigator, hit_position, momentum):
        pass

    def remove_camera(self):
        self.camera.unpossessed()

    def unpossess(self):
        self.pawn.unpossessed()

    def hear_sound(self, path, location):
        pass

    @event(ReplicableUnregisteredEvent)
    def on_unregistered(self):
        super().on_unregistered()

        if self.pawn:
            self.pawn.request_unregistration()
            self.camera.request_unregistration()

            self.remove_camera()
            self.unpossess()

    def possess(self, replicable):

        self.pawn = replicable
        self.pawn.possessed_by(self)

        CollisionEvent.set_parent(self, self.pawn)

    def set_camera(self, camera):
        self.camera = camera
        self.camera.possessed_by(self)

        camera_socket = self.pawn.sockets['camera']
        camera.parent_to(camera_socket)

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
        if not self.weapon.can_fire or not self.camera:
            return

        self.weapon.fire(self.camera)

        for controller in WorldInfo.subclass_of(Controller):
            if controller == self:
                continue

            controller.hear_sound(self.weapon.shoot_sound,
                                  self.pawn.position)


class ReplicableInfo(Replicable):

    @event(ReplicableInstantiatedEvent)
    def on_initialised(self):
        super().on_initialised()

        self.always_relevant = True


class PlayerReplicationInfo(ReplicableInfo):

    name = Attribute("")


class AIController(Controller):

    @event(ReplicableInstantiatedEvent)
    def on_initialised(self):
        super().on_initialised()
        self.hear_range = 15
        self.effective_hear = 10

        self.target_dir = None
        self.target = None

        self.navmesh = None

        self.setup_states(self.state_manager)

    @event(CollisionEvent)
    def on_collision(self, actor, new_collision):
        if new_collision and isinstance(actor, NavmeshObject):
            navmesh = next(i for i in WorldInfo.subclass_of(Navmesh) if i.object == actor)
            self.navmesh = navmesh
            print(navmesh)

    def leave_alert_to_idle(self, state):
        return self.alert_timer == 0

    def enter_engage_from_alert(self, state):
        self.target = found_target = self.get_visible()
        if found_target:
            self.target_dir = found_target.position - self.pawn.position
        return found_target is not None

    def leave_engage_state_to_alert(self, state):
        return not self.target.registered or self.target.health == 0.0

    def setup_states(self, state_machine):
        state_machine.add_state(AIState.idle, self.handle_idle)
        state_machine.add_state(AIState.alert, self.handle_alerted)
        state_machine.add_state(AIState.engage, self.handle_engaging)

        state_machine.add_branch(AIState.alert, AIState.idle,
                                 self.leave_alert_to_idle)
        #state_machine.add_branch(AIState.idle, AIState.alert,
                              #   self.enter_engage_from_alert)
       # state_machine.add_branch(AIState.alert, AIState.engage,
                       #          self.enter_engage_from_alert)
        state_machine.add_branch(AIState.engage, AIState.alert,
                                 self.leave_engage_state_to_alert)

        self.alert_timer = Timer(target_value=0.0, count_down=True)
        state_machine.current_state = AIState.idle

    def on_alerted(self, direction):
        self.target_dir = direction
        self.alert_timer.value = 10

        if self.state_manager.current_state.identifier == AIState.idle:
            self.state_manager.current_state = AIState.alert

    def take_damage(self, damage, instigator, hit_position, momentum):
        # Set alert
        self.on_alerted(-momentum)

    def hear_sound(self, path, source):
        probability = falloff_fraction(self.pawn.position,
                            self.hear_range,
                            source,
                            self.effective_hear)

        if probability > 0.5:
            self.on_alerted(source - self.pawn.position)

    def get_visible(self, ignore_self=True):
        if not self.camera:
            return

        sees = self.camera.sees_actor

        for actor in WorldInfo.subclass_of(Pawn):
            if actor == self.pawn and ignore_self:
                continue
            if sees(actor):
                return actor

    def handle_idle(self, state, delta_time):
        pass

    def handle_engaging(self, state, delta_time):
        target_vector = self.target.position - self.camera.position

        if self.pawn.navmesh:
            path = self.pawn.navmesh.find_path(self.pawn.position,
                                               self.target.posiiton)
            self.pawn.follow_path(path)
        else:
            self.pawn.move_to(self.target.position)

        self.start_server_fire()

    def handle_alerted(self, state, delta_time):
        self.alert_timer.update(delta_time)

    @event(UpdateEvent, True)
    @simulated
    def update(self, delta_time):
        self.state_manager.current_state.run(delta_time)


class PlayerController(Controller):

    input_fields = []

    move_error_limit = 0.5 ** 2
    config_filepath = "inputs.conf"

    def receive_broadcast(self, sender: StaticValue(Replicable),
                  message_string:StaticValue(str)) -> Netmodes.client:
        print("BROADCAST: {}".format(message_string))

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

        PhysicsSingleUpdate.invoke(delta_time, target=self.pawn)

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
        assert set(self.input_fields).issubset(bindings)

        print("Loaded {} keybindings".format(len(bindings)))
        return bindings

    @event(ReplicableInstantiatedEvent)
    def on_initialised(self):
        super().on_initialised()
        self.setup_input()

        self.current_move_id = 0
        self.previous_moves = OrderedDict()

        self.mouse_setup = False
        self.camera_setup = False

    @simulated
    @event(PlayerInputEvent, True)
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
        super().possess(replicable)

        PhysicsUnsetSimulated.invoke(target=replicable)

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

    def server_validate(self, move_id:StaticValue(int),
                            inputs: StaticValue(InputManager,
                                        class_data={"fields": "input_fields"}),
                            mouse_diff_x: StaticValue(float),
                            mouse_diff_y: StaticValue(float),
                            delta_time: StaticValue(float),
                            position: StaticValue(Vector),
                            rotation: StaticValue(Euler)
                        ) -> Netmodes.server:

        self.current_move_id = move_id

        self.execute_move(inputs, mouse_diff_x, mouse_diff_y, delta_time)

        self.save_move(move_id, delta_time, inputs.to_tuple(), mouse_diff_x,
                       mouse_diff_y)

        correction = self.get_corrected_state(position, rotation)

        if correction is None:
            self.acknowledge_good_move(self.current_move_id)

        else:
            self.correct_bad_move(self.current_move_id, correction)

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
        PhysicsSetSimulated.invoke(target=self.pawn)

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

    @event(ReplicableInstantiatedEvent)
    def on_initialised(self):
        super().on_initialised()

        self.object = self.actor_class(self.entity_name)
        self.update_simulated_physics = True
        self.always_relevant = False
        self.camera_radius = 1

    @event(ReplicableUnregisteredEvent)
    def on_unregistered(self):
        super().on_unregistered()
        self.object.endObject()

    def on_notify(self, name):
        if name == "rigid_body_state":
            PhysicsReplicatedEvent.invoke(self.rigid_body_state, target=self)
        else:
            super().on_notify(name)

    def take_damage(self, damage, instigator, hit_position, momentum):
        print("Take damage")
        self.health = max(self.health - damage, 0)

    @simulated
    def align_to(self, vector, time, axis=Axis.y):
        self.object.alignAxisToVect(vector, axis, time)

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
    ammo = Attribute(7)

    @event(ReplicableInstantiatedEvent)
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

    @run_on(Netmodes.server)
    def instant_shot(self, camera):
        hit_object, hit_position, hit_normal = camera.trace_ray(
                                                self.maximum_range)

        camera.draw()

        if not hit_object:
            return

        for replicable in WorldInfo.subclass_of(Actor):
            if replicable.object == hit_object:
                break
        else:
            return

        hit_vector = (hit_position - camera.position)

        falloff = falloff_fraction(camera.position,
                                    self.maximum_range,
                                    hit_position, self.effective_range)

        damage = self.base_damage * falloff

        momentum = self.momentum * hit_vector.normalized() * falloff

        replicable.take_damage(damage, self.owner, hit_position, momentum)

    @property
    def sound_folder(self):
        return path.join(self.sound_path, self.__class__.__name__)

    @property
    def shoot_sound(self):
        return path.join(self.sound_folder, "shoot.wav")


class EmptyWeapon(Weapon):

    ammo = Attribute(0)

    @event(ReplicableInstantiatedEvent)
    def on_initialised(self):
        super().on_initialised()

        self.attachment_class = EmptyAttatchment


class WeaponAttachment(Actor):

    roles = Attribute(Roles(Roles.authority, Roles.none))

    @event(ReplicableInstantiatedEvent)
    def on_initialised(self):
        super().on_initialised()

        self.update_simulated_physics = False

    def play_fire_effects(self):
        pass


class EmptyAttatchment(WeaponAttachment):
    entity_name = "Empty.002"

    def play_fire_effects(self):
        pass


class Camera(Actor):

    entity_name = "Camera"
    actor_class = CameraObject

    @event(ReplicableRegisteredEvent)
    def on_registered(self):
        super().on_registered()
        self._visible = True

    @property
    def visible(self):
        return self._visible

    @visible.setter
    def visible(self, value):
        self._visible = value

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
        scene.active_camera = old_camera

    def sees_actor(self, replicable):
        if replicable.camera_radius < 0.5:
            return self.object.pointInsideFrustum(replicable.position)

        return self.object.sphereInsideFrustum(replicable.position,
                           replicable.camera_radius) != self.object.OUTSIDE

    @simulated
    @event(UpdateEvent, True)
    def update(self, delta_time):
        if not self.visible:
            return

        self.draw()

    def trace(self, x_coord, y_coord, distance=0):
        return self.object.getScreenRay(x_coord, y_coord, distance)

    def trace_ray(self, distance=0):
        target = Vector((0, distance, 0))
        target.rotate(Euler((pi / 2, 0, 0)))
        target.rotate(self.rotation)
        return self.object.rayCast(target, self.position, distance)


class Pawn(Actor):

    view_pitch = Attribute(0.0)
    flash_count = Attribute(0,
                   notify=True,
                        complain=False)
    health = Attribute(100)
    weapon_attachment_class = Attribute(type_of=TypeRegister,
                                        notify=True)

    def take_damage(self, damage, instigator, hit_position, momentum):
        super().take_damage(damage, instigator, hit_position, momentum)

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
            yield "health"

    def create_weapon_attachment(self, cls):
        self.weapon_attachment = cls()
        self.weapon_attachment.parent_to(self.sockets['weapon'])

        self.weapon_attachment.local_position = Vector()
        self.weapon_attachment.local_rotation = Euler()

    def handle_animation(self, movement_mode):
        pass

    @event(ReplicableInstantiatedEvent)
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

        self.state_machine = FiniteStateMachine()
        self.targets = []
        self.target_distance = 0.3

        self.setup_states(self.state_machine)

    @simulated
    def setup_states(self, state_machine):
        state_machine.add_state("tracking", self.tracking_target)
        state_machine.add_state("empty", lambda *x: None)
        state_machine.add_branch("empty", "tracking",
                                 lambda *x: bool(self.targets))
        state_machine.add_branch("tracking", "empty",
                                 lambda *x: not bool(self.targets))
        state_machine.current_state = "empty"

    def on_notify(self, name):

        # play weapon effects
        if name == "flash_count":
            self.update_flashcount()

        elif name == "weapon_attachment_class":
            self.create_weapon_attachment(self.weapon_attachment_class)

        else:
            super().on_notify(name)

    @event(ReplicableUnregisteredEvent)
    def on_unregistered(self):
        super().on_unregistered()

        if self.weapon_attachment:
            self.weapon_attachment.request_unregistration()

    def tracking_target(self, state, delta_time):
        displacement = self.position - self.targets[0]

        if displacement.length < self.target_distance:
            self.targets.remove(0)

            if not self.targets:
                return

            displacement = self.position - self.targets[0]

        sideways = Vector((0, 0, 1)).cross(displacement)

        self.align_to(sideways, self.turn_speed, axis=Axis.x)
        self.velocity = Vector((0, 1, 0)) * self.walk_speed

    def move_to(self, target):
        self.targets.append(target)

    def follow_path(self, path):
        self.targets = path

    @simulated
    @event(UpdateEvent, True)
    def update(self, delta_time):
        if self.outstanding_flash:
            self.use_flashcount()

        if self.weapon_attachment:
            self.weapon_attachment.local_rotation = Euler((self.view_pitch, 0, 0))

        self.state_machine.current_state.run(delta_time)
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
