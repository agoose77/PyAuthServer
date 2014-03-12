from network import *

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
from . import stream
from . import physics_object

import aud
import bge
import collections

import math
import mathutils
import os
import operator
import functools

from bge import logic, types

Move = collections.namedtuple("Move", ("tick", "inputs", "mouse_x", "mouse_y"))


class Controller(Replicable):

    roles = Attribute(Roles(Roles.authority, Roles.autonomous_proxy))
    pawn = Attribute(type_of=Replicable, complain=True, notify=True)
    camera = Attribute(type_of=Replicable, complain=True, notify=True)
    weapon = Attribute(type_of=Replicable, complain=True, notify=True)
    info = Attribute(type_of=Replicable, complain=True)

    replication_priority = 2.0

    def on_initialised(self):
        super().on_initialised()

        self.hear_range = 15
        self.effective_hear_range = 10

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

    def hear_voice(self, info, voice):
        pass

    def possess(self, replicable):
        self.pawn = replicable
        self.pawn.possessed_by(self)

        if WorldInfo.netmode == Netmodes.server:
            self.info.pawn = replicable

        # Register as child for signals
        replicable.register_child(self)

    def remove_camera(self):
        self.camera.unpossessed()

    def server_fire(self):
        self.weapon.fire(self.camera)
        # Update flash count (for client-side fire effects)
        self.pawn.flash_count += 1

        if self.pawn.flash_count > 255:
            self.pawn.flash_count = 0

        for controller in WorldInfo.subclass_of(Controller):
            if controller == self:
                continue

            controller.hear_sound(self.weapon.shoot_sound,
                                self.pawn.position)

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

    def unpossess(self):
        self.pawn.unpossessed()

        self.info.pawn = self.pawn = None


class ReplicableInfo(Replicable):
    roles = Attribute(Roles(Roles.authority, Roles.simulated_proxy))

    def on_initialised(self):
        super().on_initialised()

        self.always_relevant = True


class AIReplicationInfo(ReplicableInfo):

    pawn = Attribute(type_of=Replicable, complain=True)

    def conditions(self, is_owner, is_complain, is_initial):
        yield from super().conditions(is_owner, is_complain, is_initial)

        if is_complain:
            yield "pawn"


class PlayerReplicationInfo(AIReplicationInfo):

    name = Attribute("", complain=True)
    ping = Attribute(0.0)

    def conditions(self, is_owner, is_complain, is_initial):
        yield from super().conditions(is_owner, is_complain, is_initial)

        if is_complain:
            yield "name"

        yield "ping"


class AIController(Controller):

    def get_visible(self, ignore_self=True):
        if not self.camera:
            return

        sees = self.camera.sees_actor
        my_pawn = self.pawn

        for actor in WorldInfo.subclass_of(Pawn):
            if (actor == my_pawn and ignore_self):
                continue

            elif sees(actor):
                return actor

    def unpossess(self):
        self.behaviour.reset()
        self.behaviour.blackboard['controller'] = self

        super().unpossess()

    def hear_sound(self, sound_path, source):
        if not (self.pawn and self.camera):
            return
        return
        probability = utilities.falloff_fraction(self.pawn.position,
                            self.hear_range,
                            source,
                            self.effective_hear_range)

    def on_initialised(self):
        super().on_initialised()

        self.camera_mode = enums.CameraMode.first_person
        self.behaviour = behaviour_tree.BehaviourTree(self)
        self.behaviour.blackboard['controller'] = self

    @UpdateSignal.global_listener
    def update(self, delta_time):
        self.behaviour.update()


class PlayerController(Controller):
    '''Player pawn controller network object'''

    input_fields = []

    move_error_limit = 0.2 ** 2
    config_filepath = "inputs.conf"

    @property
    def mouse_delta(self):
        '''Returns the mouse movement since the last tick'''
        mouse = logic.mouse

        # The first tick the mouse won't be centred
        screen_center = (0.5, 0.5)
        mouse_position, mouse.position = mouse.position, screen_center
        epsilon = self._mouse_epsilon
        smooth_factor = self.mouse_smoothing

        # If we have already initialised the mouse
        if self._mouse_delta is not None:
            mouse_diff_x = screen_center[0] - mouse_position[0]
            mouse_diff_y = screen_center[1] - mouse_position[1]

            smooth_x = utilities.lerp(self._mouse_delta[0],
                                    mouse_diff_x, smooth_factor)
            smooth_y = utilities.lerp(self._mouse_delta[1],
                                    mouse_diff_y, smooth_factor)
        else:
            smooth_x = smooth_y = 0.0

        # Handle near zero values (must be set to a number above zero)
        if abs(smooth_x) < epsilon:
            smooth_x = epsilon / 1000
        if abs(smooth_y) < epsilon:
            smooth_y = epsilon / 1000

        self._mouse_delta = smooth_x, smooth_y
        return smooth_x, smooth_y

    def apply_move(self, inputs, mouse_diff_x, mouse_diff_y):
        blackboard = self.behaviour.blackboard

        blackboard['inputs'] = inputs
        blackboard['mouse'] = mouse_diff_x, mouse_diff_y

        self.behaviour.update()

    @requires_netmode(Netmodes.server)
    def calculate_ping(self):
        if not self.is_locked("ping"):
            self.client_reply_ping(WorldInfo.tick)
            self.server_add_lock("ping")

    def client_adjust_tick(self) -> Netmodes.client:
        self.server_remove_lock("clock")
        self.client_request_time(WorldInfo.elapsed)

    def client_acknowledge_move(self, move_tick: TypeFlag(int,
                                max_value=WorldInfo._MAXIMUM_TICK)) -> Netmodes.client:
        if not self.pawn:
            print("Could not find Pawn for {}".format(self))
            return

        try:
            self.pending_moves.pop(move_tick)

        except KeyError:
            print("Couldn't find move to acknowledge for move {}"
                .format(move_tick))
            return

        additional_keys = [k for k in self.pending_moves if k < move_tick]

        for key in additional_keys:
            self.pending_moves.pop(key)

        return True

    def client_apply_correction(self, correction_tick: TypeFlag(int,
                               max_value=WorldInfo._MAXIMUM_TICK),
                                correction: TypeFlag(structs.RigidBodyState)) -> Netmodes.client:
        if not self.pawn:
            print("Could not find Pawn for {}".format(self))
            return

        # Remove the lock at this network tick on server
        self.server_remove_buffered_lock(WorldInfo.tick, "correction")

        if not self.client_acknowledge_move(correction_tick):
            print("No move found")
            return

        signals.PhysicsCopyState.invoke(correction, self.pawn)
        print("{}: Correcting prediction for move {}".format(self,
                                                             correction_tick))

        # Interface inputs with existing ones
        lookup_dict = {}
        apply_move = self.apply_move

        with self.inputs.using_interface(lookup_dict.__getitem__):
            for move in self.pending_moves.values():
                # Place inputs into input manager
                inputs_zip = zip(sorted(self.inputs.keybindings), move.inputs)
                lookup_dict.update(inputs_zip)

                apply_move(self.inputs, move.mouse_x, move.mouse_y)
                signals.PhysicsSingleUpdateSignal.invoke(1 / WorldInfo.tick_rate,
                                                         target=self.pawn)

    @requires_netmode(Netmodes.client)
    def client_fire(self):
        self.pawn.weapon_attachment.play_fire_effects()
        self.hear_sound(self.weapon.shoot_sound, self.pawn.position)
        self.weapon.fire(self.camera)

    def client_nudge_clock(self, difference:TypeFlag(int, max_value=WorldInfo._MAXIMUM_TICK),
                           forward: TypeFlag(bool)) -> Netmodes.client:
        # Update clock
        sign = (-1 + (forward * 2))
        WorldInfo.elapsed += (difference * sign) / WorldInfo.tick_rate

        # Reply received correction
        self.server_remove_buffered_lock(WorldInfo.tick, "clock_synch")

    def client_reply_ping(self, tick: TypeFlag(int, max_value=WorldInfo._MAXIMUM_TICK)) -> Netmodes.client:
        self.server_deduce_ping(tick)

    @requires_netmode(Netmodes.client)
    def client_send_move(self):
        # Get move information
        current_tick = WorldInfo.tick
        try:
            move = self.pending_moves[current_tick]
        except KeyError:
            return

        self.server_store_move(current_tick, self.inputs,
                               move.mouse_x,
                               move.mouse_y,
                               self.pawn.position,
                               self.pawn.rotation)

    @requires_netmode(Netmodes.client)
    def destroy_microphone(self):
        del self.microphone
        for key in list(self.sound_channels):
            del self.sound_channels[key]

    def get_clock_correction(self, current_tick, command_tick):
        return int((current_tick - command_tick) * self.clock_convergence_factor)

    def get_corrected_state(self, position, rotation):
        pos_difference = self.pawn.position - position

        if pos_difference.length_squared <= self.move_error_limit:
            return

        # Create correction if neccessary
        correction = structs.RigidBodyState()
        signals.PhysicsCopyState.invoke(self.pawn, correction)

        return correction

    def hear_sound(self, sound_path: TypeFlag(str),
                   source: TypeFlag(mathutils.Vector)) -> Netmodes.client:
        if not (self.pawn and self.camera):
            return

        probability = utilities.falloff_fraction(self.pawn.position,
                                                self.hear_range, source,
                                                self.effective_hear_range)
        return
        factory = aud.Factory.file(sound_path)
        return aud.device().play(factory)

    def hear_voice(self, info: TypeFlag(Replicable),
                        data: TypeFlag(bytes, max_length=2**32 - 1)) -> Netmodes.client:
        player = self.sound_channels[info]
        player.decode(data)

    def is_locked(self, name):
        return name in self.locks

    def load_keybindings(self):
        bindings = configuration.load_configuration(self.config_filepath,
                                    self.__class__.__name__,
                                    self.input_fields)
        print("Loaded {} keybindings".format(len(bindings)))
        return bindings

    def on_initialised(self):
        super().on_initialised()

        self.setup_input()
        self.setup_microphone()

        self.pending_moves = collections.OrderedDict()

        self.camera_setup = False
        self.mouse_smoothing = 0.6

        self._mouse_delta = None
        self._mouse_epsilon = 0.001

        self.behaviour = behaviour_tree.BehaviourTree(self)
        self.behaviour.blackboard['controller'] = self

        self.locks = set()
        self.buffered_locks = FactoryDict(dict,
                                          dict_type=collections.OrderedDict,
                                          provide_key=False)

        self.buffer = collections.deque()

        self.clock_convergence_factor = 1.0
        self.maximum_clock_ahead = int(0.05 * WorldInfo.tick_rate)

        self.ping_timer = timer.Timer(1.0, on_target=self.calculate_ping,
                                    repeat=True)
        self.ping_influence_factor = 0.8

        self._last_pawn = None

    def on_notify(self, name):
        if name == "pawn":
            if self.pawn:
                if self._last_pawn is not None:
                    self._last_pawn.unpossessed()

                self.possess(self.pawn)
                self._last_pawn = self.pawn
            else:
                self.unpossess()

        elif name == "camera":
            #assert self.pawn
            self.set_camera(self.camera)
            self.camera.active = True

        elif name == "weapon":
            self.set_weapon(self.weapon)

        else:
            super().on_notify(name)

    def on_unregistered(self):
        super().on_unregistered()
        self.destroy_microphone()

    @signals.PlayerInputSignal.global_listener
    def player_update(self, delta_time):
        '''Update function for client instance'''
        if not (self.pawn and self.camera):
            return

        # Control Mouse data
        mouse_diff_x, mouse_diff_y = self.mouse_delta
        current_tick = WorldInfo.tick

        # Apply move inputs
        self.apply_move(self.inputs, mouse_diff_x, mouse_diff_y)

        # Remember move for corrections
        self.pending_moves[current_tick] = Move(current_tick,
                 self.inputs.to_tuple(), mouse_diff_x, mouse_diff_y)
        self.broadcast_voice()

    @signals.PostPhysicsSignal.global_listener
    def post_physics(self):
        '''Post move to server and receive corrections'''
        self.client_send_move()
        self.server_check_move()

    def receive_broadcast(self, message_string: TypeFlag(str)) -> Netmodes.client:
        BroadcastMessage.invoke(message_string)

    def send_voice_server(self, data: TypeFlag(bytes,
                                            max_length=2**32 - 1)) -> Netmodes.server:
        info = self.info
        for controller in WorldInfo.subclass_of(Controller):
            if controller is self:
                continue

            controller.hear_voice(info, data)

    def server_deduce_ping(self, tick: TypeFlag(int, max_value=WorldInfo._MAXIMUM_TICK)) -> Netmodes.server:
        round_trip_tick = WorldInfo.tick - tick
        round_trip_time = round_trip_tick / WorldInfo.tick_rate
        self.info.ping = (((1 - self.ping_influence_factor) * self.info.ping)
                          + (self.ping_influence_factor * round_trip_time))
        self.server_remove_lock("ping")

    @requires_netmode(Netmodes.server)
    def server_fire(self):
        print("Rolling back by {:.3f} seconds".format(self.info.ping))
        if 0:
            latency_ticks = WorldInfo.to_ticks(self.info.ping) + 1
            signals.PhysicsRewindSignal.invoke(WorldInfo.tick - latency_ticks)

        super().server_fire()

        if 0:
            signals.PhysicsRewindSignal.invoke()

    def server_remove_lock(self, name: TypeFlag(str)) -> Netmodes.server:
        '''Flag a variable as unlocked on the server'''
        try:
            self.locks.remove(name)
        except KeyError:
            print("{} was not locked".format(name))

    def server_add_lock(self, name: TypeFlag(str)) -> Netmodes.server:
        '''Flag a variable as locked on the server'''
        self.locks.add(name)

    def server_remove_buffered_lock(self, tick: TypeFlag(int, max_value=WorldInfo._MAXIMUM_TICK),
                                    name: TypeFlag(str)) -> Netmodes.server:
        '''Remove a server lock with respect for the jitter offset'''
        self.buffered_locks[tick][name] = False

    def server_add_buffered_lock(self, tick: TypeFlag(int, max_value=WorldInfo._MAXIMUM_TICK),
                                    name: TypeFlag(str)) -> Netmodes.server:
        '''Add a server lock with respect for the jitter offset'''
        self.buffered_locks[tick][name] = True

    def server_store_move(self, tick: TypeFlag(int, max_value=WorldInfo._MAXIMUM_TICK),
                                inputs: TypeFlag(inputs.InputManager,
                                input_fields=MarkAttribute("input_fields")),
                                mouse_diff_x: TypeFlag(float),
                                mouse_diff_y: TypeFlag(float),
                                position: TypeFlag(mathutils.Vector),
                                rotation: TypeFlag(mathutils.Euler)) -> Netmodes.server:
        '''Store a client move for later processing and clock validation'''

        current_tick = WorldInfo.tick
        target_tick = self.maximum_clock_ahead + current_tick

        # If the move is too early, correct clock
        if tick > target_tick:
            self.update_buffered_locks(tick)
            self.start_clock_correction(target_tick, tick)
            return

        data = (inputs, mouse_diff_x, mouse_diff_y, position, rotation)
        self.buffer.append((tick, data))

    @requires_netmode(Netmodes.server)
    def server_check_move(self):
        """Check result of movement operation following Physics update"""
        # Get move information
        current_tick = WorldInfo.tick

        # We are forced to acknowledge moves whose base we've already corrected
        if self.is_locked("correction"):
            self.client_acknowledge_move(current_tick)
            return

        # Validate move
        try:
            position, rotation = self.pending_moves[current_tick]

        except KeyError:
            return

        correction = self.get_corrected_state(position, rotation)

        # It was a valid move
        if correction is None:
            self.client_acknowledge_move(current_tick)

        # Send the correction
        else:
            self.server_add_lock("correction")
            self.client_apply_correction(current_tick, correction)

    @requires_netmode(Netmodes.client)
    def setup_input(self):
        '''Create the input manager for the client'''
        keybindings = self.load_keybindings()

        self.inputs = inputs.InputManager(keybindings)
        print("Created input manager")

    @requires_netmode(Netmodes.client)
    def setup_microphone(self):
        '''Create the microphone for the client'''
        self.microphone = stream.MicrophoneStream()
        self.sound_channels = collections.defaultdict(stream.SpeakerStream)

    def set_name(self, name: TypeFlag(str)) -> Netmodes.server:
        self.info.name = name

    def start_clock_correction(self, current_tick, command_tick):
        '''Initiate client clock correction'''
        if not self.is_locked("clock_synch"):
            tick_difference = self.get_clock_correction(current_tick, command_tick)
            nudge_forward = current_tick > command_tick
            self.client_nudge_clock(abs(tick_difference), forward=nudge_forward)
            self.server_add_lock("clock_synch")

    def start_fire(self):
        if not self.weapon:
            return

        if not self.weapon.can_fire or not self.camera:
            return

        self.server_fire()
        self.client_fire()

    def broadcast_voice(self):
        '''Dump voice information and encode it for the server'''
        data = self.microphone.encode()
        if data:
            self.send_voice_server(data)

    @requires_netmode(Netmodes.server)
    @UpdateSignal.global_listener
    def update(self, delta_time):
        '''Validate client clock and apply moves'''
        # Aim ahead by the jitter buffer size
        current_tick = WorldInfo.tick
        target_tick = self.maximum_clock_ahead + current_tick
        consume_move = self.buffer.popleft

        try:
            tick, (inputs, mouse_diff_x, mouse_diff_y,
                   position, rotation) = self.buffer[0]

        except IndexError:
            return

        # Process any buffered locks
        self.update_buffered_locks(tick)

        # The tick is late, try and run a newer command
        if tick < current_tick:
            # Ensure we check through to the latest tick
            consume_move()

            if self.buffer:
                self.update(delta_time)

            else:
                self.start_clock_correction(target_tick, tick)

        # If the tick is early, wait for it to become valid
        elif tick > current_tick:
            return

        # Else run the move at the present time (it's valid)
        else:
            consume_move()

            if not (self.pawn and self.camera):
                return

            # Apply move inputs
            self.apply_move(inputs, mouse_diff_x, mouse_diff_y)
            # Save expected move results
            self.pending_moves[current_tick] = position, rotation

    def update_buffered_locks(self, tick):
        '''Apply server lock changes for the jitter buffer tick'''
        removed_keys = []
        for tick_, locks in self.buffered_locks.items():
            if tick_ > tick:
                break

            for lock_name, add_lock in locks.items():
                if add_lock:
                    self.server_add_lock(lock_name)
                else:
                    self.server_remove_lock(lock_name)

            removed_keys.append(tick_)

        for key in removed_keys:
            self.buffered_locks.pop(key)


class Actor(Replicable, physics_object.PhysicsObject):
    '''Physics enabled network object'''

    rigid_body_state = Attribute(structs.RigidBodyState(), notify=True)
    roles = Attribute(Roles(Roles.authority, Roles.simulated_proxy),
                    notify=True)

    def conditions(self, is_owner, is_complaint, is_initial):
        yield from super().conditions(is_owner, is_complaint, is_initial)

        remote_role = self.roles.remote

        # If simulated, send rigid body state
        if (remote_role == Roles.simulated_proxy) or \
            (remote_role == Roles.dumb_proxy) or \
            (self.roles.remote == Roles.autonomous_proxy and not is_owner):
            if self.update_simulated_physics or is_initial:
                yield "rigid_body_state"

    def on_initialised(self):
        super().on_initialised()

        self.camera_radius = 1

        self.update_simulated_physics = True
        self.always_relevant = False

    def on_unregistered(self):
        # Unregister any actor children
        for child in self.children:
            child.request_unregistration()

        super().on_unregistered()

    def on_notify(self, name):
        if name == "rigid_body_state":
            signals.PhysicsReplicatedSignal.invoke(self.rigid_body_state, target=self)
        else:
            super().on_notify(name)

    @simulated
    def trace_ray(self, local_vector):
        target = self.transform * local_vector

        return self.object.rayCast(self.object, target)

    @simulated
    def align_to(self, vector, time=1, axis=enums.Axis.y):
        if not vector:
            return
        self.object.alignAxisToVect(vector, axis, time)


class Weapon(Replicable):
    roles = Attribute(Roles(Roles.authority, Roles.autonomous_proxy))
    ammo = Attribute(70, notify=True)

    @property
    def can_fire(self):
        return (bool(self.ammo) and (WorldInfo.tick - self.last_fired_tick)
                >= (self.shoot_interval * WorldInfo.tick_rate))

    @property
    def data_path(self):
        return os.path.join(self._data_path, self.__class__.__name__)

    @property
    def shoot_sound(self):
        return os.path.join(self.data_path, "sounds/shoot.wav")

    @property
    def icon_path(self):
        return os.path.join(self.data_path, "icon/icon.tga")

    def consume_ammo(self):
        self.ammo -= 1

    def fire(self, camera):
        self.consume_ammo()
        self.last_fired_tick = WorldInfo.tick

    def conditions(self, is_owner, is_complaint, is_initial):
        yield from super().conditions(is_owner, is_complaint, is_initial)

        yield "ammo"

    def on_initialised(self):
        super().on_initialised()

        self._data_path = logic.expandPath("//data")
        self.shoot_interval = 0.5
        self.last_fired_tick = 0
        self.max_ammo = 70

        self.momentum = 1
        self.maximum_range = 20
        self.effective_range = 10
        self.base_damage = 40

        self.attachment_class = None


class TraceWeapon(Weapon):

    def fire(self, camera):
        super().fire(camera)

        self.trace_shot(camera)

    @requires_netmode(Netmodes.server)
    def trace_shot(self, camera):
        hit_object, hit_position, hit_normal = camera.trace_ray(
                                                self.maximum_range)
        if not hit_object:
            return

        replicable = Actor.from_object(hit_object)

        if replicable == self.owner.pawn or not isinstance(replicable, Pawn):
            return

        hit_vector = (hit_position - camera.position)
        falloff = utilities.falloff_fraction(camera.position,
                                    self.maximum_range,
                                    hit_position, self.effective_range)
        damage = self.base_damage * falloff
        momentum = self.momentum * hit_vector.normalized() * falloff

        signals.ActorDamagedSignal.invoke(damage, self.owner, hit_position,
                                momentum, target=replicable)


class ProjectileWeapon(Weapon):

    def on_initialised(self):
        super().on_initialised()

        self.projectile_class = None
        self.projectile_velocity = mathutils.Vector()

    def fire(self, camera):
        super().fire(camera)

        self.projectile_shot(camera)

    @requires_netmode(Netmodes.server)
    def projectile_shot(self, camera):
        projectile = self.projectile_class()
        forward_vector = mathutils.Vector((0, 1, 0))
        forward_vector.rotate(camera.rotation)
        projectile.position = camera.position + forward_vector * 6.0
        projectile.rotation = camera.rotation.copy()
        projectile.velocity = self.projectile_velocity
        projectile.owner = self


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

    entity_class = bge_data.CameraObject
    entity_name = "Camera"

    roles = Attribute(Roles(Roles.authority, Roles.autonomous_proxy),
                    notify=True)

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

    @property
    def rotation(self):
        rotation = mathutils.Euler((-math.radians(90), 0, 0))
        rotation.rotate(self.object.worldOrientation)
        return rotation

    @rotation.setter
    def rotation(self, rot):
        rotation = mathutils.Euler((math.radians(90), 0, 0))
        rotation.rotate(rot)
        self.object.worldOrientation = rotation

    @property
    def local_rotation(self):
        rotation = mathutils.Euler((-math.radians(90), 0, 0))
        rotation.rotate(self.object.localOrientation)
        return rotation

    @local_rotation.setter
    def local_rotation(self, rot):
        rotation = mathutils.Euler((math.radians(90), 0, 0))
        rotation.rotate(rot)
        self.object.localOrientation = rotation

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

        self.local_rotation = mathutils.Euler()

    def sees_actor(self, actor):
        try:
            radius = actor.camera_radius

        except AttributeError:
            return

        if radius < 0.5:
            return self.object.pointInsideFrustum(actor.position)

        return self.object.sphereInsideFrustum(actor.position, radius) != self.object.OUTSIDE

    @simulated
    @UpdateSignal.global_listener
    def update(self, delta_time):
        if self.visible:
            self.draw()

    def trace(self, x_coord, y_coord, distance=0):
        return self.object.getScreenRay(x_coord, y_coord, distance)

    def trace_ray(self, distance=0):
        target = self.transform * mathutils.Vector((0, 0, -distance))
        return self.object.rayCast(target, self.position, distance)


class Pawn(Actor):
    view_pitch = Attribute(0.0)
    flash_count = Attribute(0)
    weapon_attachment_class = Attribute(type_of=type(Replicable),
                                        notify=True,
                                        complain=True)

    health = Attribute(100, notify=True, complain=True)
    alive = Attribute(True, notify=True, complain=True)
    roles = Attribute(Roles(Roles.authority, Roles.autonomous_proxy),
                    notify=True)

    replication_update_period = 1 / 60

    def conditions(self, is_owner, is_complaint, is_initial):
        yield from super().conditions(is_owner, is_complaint, is_initial)

        if not is_owner:
            yield "view_pitch"
            yield "flash_count"

        if is_complaint:
            yield "weapon_attachment_class"
            yield "alive"

            if is_owner:
                yield "health"

    @simulated
    def create_weapon_attachment(self, cls):
        self.weapon_attachment = cls()
        self.weapon_attachment.set_parent(self, "weapon")

        if self.weapon_attachment is not None:
            self.weapon_attachment.unpossessed()
        self.weapon_attachment.possessed_by(self)

        self.weapon_attachment.local_position = mathutils.Vector()
        self.weapon_attachment.local_rotation = mathutils.Euler()

    @simulated
    def get_animation_frame(self, layer=0):
        return int(self.skeleton.getActionFrame(layer))

    @simulated
    def is_playing_animation(self, layer=0):
        return self.skeleton.isPlayingAction(layer)

    @property
    def on_ground(self):
        for collider in self._registered:
            if not self.from_object(collider):
                return True
        return False

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

    @simulated
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

    @simulated
    def play_animation(self, name, start, end, layer=0, priority=0, blend=0,
                    mode=enums.AnimationMode.play, weight=0.0, speed=1.0,
                    blend_mode=enums.AnimationBlend.interpolate):

        # Define conversions from Blender animations to Network animation enum
        ge_mode = {enums.AnimationMode.play: logic.KX_ACTION_MODE_PLAY,
                enums.AnimationMode.loop: logic.KX_ACTION_MODE_LOOP,
                enums.AnimationMode.ping_pong: logic.KX_ACTION_MODE_PING_PONG
                }[mode]
        ge_blend_mode = {enums.AnimationBlend.interpolate: logic.KX_ACTION_BLEND_BLEND,
                        enums.AnimationBlend.add: logic.KX_ACTION_BLEND_ADD}[blend_mode]

        self.skeleton.playAction(name, start, end, layer, priority, blend,
                                ge_mode, weight, speed=speed,
                                blend_mode=ge_blend_mode)

    @simulated
    def stop_animation(self, layer=0):
        self.skeleton.stopAction(layer)

    @property
    def skeleton(self):
        for child in self.object.childrenRecursive:
            if isinstance(child, types.BL_ArmatureObject):
                return child

    @signals.ActorDamagedSignal.listener
    def take_damage(self, damage, instigator, hit_position, momentum):
        self.health = int(max(self.health - damage, 0))

    @simulated
    @UpdateSignal.global_listener
    def update(self, delta_time):
        if self.weapon_attachment:
            self.update_weapon_attachment()

        # Allow remote players to determine if we are alive without seeing health
        self.update_alive_status()
        self.animations.update()

    def update_alive_status(self):
        '''Update health boolean
        Runs on authority / autonomous proxy only'''
        self.alive = self.health > 0

    @simulated
    def update_weapon_attachment(self):
        # Account for missing shots
        if self.flash_count != self.last_flash_count:
            # Protect from wrap around
            if self.last_flash_count > self.flash_count:
                self.last_flash_count = -1

            self.weapon_attachment.play_fire_effects()
            self.last_flash_count += 1

        self.weapon_attachment.local_rotation = mathutils.Euler(
                                                        (self.view_pitch, 0, 0)
                                                        )


class Lamp(Actor):
    roles = Roles(Roles.authority, Roles.simulated_proxy)

    entity_class = bge_data.LampObject
    entity_name = "Lamp"

    def on_initialised(self):
        super().on_initialised()

        self._intensity = None

    @property
    def intensity(self):
        return self.object.energy

    @intensity.setter
    def intensity(self, energy):
        self.object.energy = energy

    @property
    def active(self):
        return not self.intensity

    @active.setter
    def active(self, state):
        '''Modifies the lamp state by setting the intensity to a placeholder

        :param state: enabled state'''

        if not (state != (self._intensity is None)):
            return

        if state:
            self._intensity, self.intensity = None, self._intensity
        else:
            self._intensity, self.intensity = self.intensity, None


class Navmesh(Actor):
    roles = Roles(Roles.authority, Roles.none)

    entity_class = bge_data.NavmeshObject
    entity_name = "Navmesh"

    def draw(self):
        self.object.draw(logic.RM_TRIS)

    def find_path(self, from_point, to_point):
        return self.object.findPath(from_point, to_point)

    def get_wall_intersection(self, from_point, to_point):
        return self.object.raycast(from_point, to_point)
