from network.bitfield import BitField
from network.decorators import requires_netmode, simulated
from network.descriptors import Attribute, TypeFlag, MarkAttribute
from network.enums import Netmodes, Roles
from network.network_struct import Struct
from network.replicable import Replicable
from network.signals import UpdateSignal
from network.structures import FactoryDict
from network.world_info import WorldInfo

from aud import Factory, device as Device
from bge import logic, types
from collections import deque, defaultdict, namedtuple, OrderedDict
from functools import partial
from math import pi
from mathutils import Vector, Euler

from .behaviour_tree import BehaviourTree
from .configuration import load_keybindings
from .enums import *
from .inputs import BGEInputStatusLookup, InputManager
from .object_types import *
from .signals import *
from .stream import MicrophoneStream, SpeakerStream
from .structs import RigidBodyState
from .timer import Timer
from .utilities import lerp, square_falloff

__all__ = ['Controller', 'PlayerController', 'AIController']


MAX_32BIT_INT = 2 ** 32 - 1


class Controller(Replicable):

    roles = Attribute(Roles(Roles.authority, Roles.autonomous_proxy))
    pawn = Attribute(type_of=Replicable, complain=True, notify=True)
    camera = Attribute(type_of=Replicable, complain=True, notify=True)
    weapon = Attribute(type_of=Replicable, complain=True, notify=True)
    info = Attribute(type_of=Replicable, complain=True)

    def attach_camera(self, camera):
        camera.set_parent(self.pawn, "camera")
        camera.local_position = Vector()

    def conditions(self, is_owner, is_complaint, is_initial):
        yield from super().conditions(is_owner, is_complaint, is_initial)

        if is_complaint:
            yield "pawn"
            yield "camera"
            yield "weapon"
            yield "info"

    def hear_voice(self, info, voice):
        pass

    def on_camera_updated(self):
        if self.camera:
            self.attach_camera(self.camera)

    def on_initialised(self):
        super().on_initialised()

        self.hear_range = 15
        self.effective_hear_range = 10
        self.replication_priority = 2.0

    def on_pawn_updated(self):
        if self.pawn:
            self.pawn.register_child(self, greedy=True)

    def on_unregistered(self):
        self.remove_dependencies()

        super().on_unregistered()

    def possess(self, replicable):
        self.pawn = replicable
        self.pawn.possessed_by(self)
        self.info.pawn = replicable

        self.on_pawn_updated()

    def remove_dependencies(self):
        if self.pawn:
            self.pawn.request_unregistration()
            self.unpossess()

        if self.weapon:
            self.weapon.request_unregistration()
            self.weapon.unpossessed()

        if self.camera:
            self.camera.request_unregistration()
            self.camera.unpossessed()

        self.camera = self.weapon = None

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
        self.camera = camera
        self.camera.possessed_by(self)

        self.on_camera_updated()

    def set_weapon(self, weapon):
        self.weapon = weapon
        self.weapon.possessed_by(self)
        self.pawn.weapon_attachment_class = weapon.attachment_class

    def unpossess(self):
        self.pawn.unpossessed()
        self.info.pawn = self.pawn = None

        self.on_pawn_updated()


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
        probability = square_falloff(self.pawn.position,
                            self.hear_range,
                            source,
                            self.effective_hear_range)

    def on_initialised(self):
        super().on_initialised()

        self.camera_mode = CameraMode.first_person
        self.behaviour = behaviour_tree.BehaviourTree(self)
        self.behaviour.blackboard['controller'] = self

    @UpdateSignal.global_listener
    def update(self, delta_time):
        self.behaviour.update()


class PlayerController(Controller):
    '''Player pawn controller network object'''

    movement_struct = None
    config_filepath = "inputs.conf"

    max_position_difference_squared = 0.5
    max_rotation_difference_squared = ((2 * pi) / 60) ** 2

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

            smooth_x = lerp(self._mouse_delta[0],
                                    mouse_diff_x, smooth_factor)
            smooth_y = lerp(self._mouse_delta[1],
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

    def apply_move(self, move):
        blackboard = self.behaviour.blackboard

        blackboard['inputs'] = move.inputs
        blackboard['mouse'] = move.mouse_x, move.mouse_y

        self.behaviour.update()

    def broadcast_voice(self):
        '''Dump voice information and encode it for the server'''
        data = self.microphone.encode()
        if data:
            self.send_voice_server(data)

    @requires_netmode(Netmodes.server)
    def calculate_ping(self):
        if not self.is_locked("ping"):
            self.client_reply_ping(WorldInfo.tick)
            self.server_add_lock("ping")

    def client_adjust_tick(self) -> Netmodes.client:
        self.server_remove_lock("clock")
        self.client_request_time(WorldInfo.elapsed)

    def client_acknowledge_move(self,
                move_tick: TypeFlag(int, max_value=WorldInfo._MAXIMUM_TICK)) -> Netmodes.client:
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

    def client_apply_correction(self,
                    correction_tick: TypeFlag(int, max_value=WorldInfo._MAXIMUM_TICK),
                    correction: TypeFlag(RigidBodyState)) -> Netmodes.client:
        # Remove the lock at this network tick on server
        self.server_remove_buffered_lock(WorldInfo.tick, "correction")

        if not self.pawn:
            print("Could not find Pawn for {}".format(self))
            return

        if not self.client_acknowledge_move(correction_tick):
            print("No move found")
            return

        PhysicsCopyState.invoke(correction, self.pawn)
        print("{}: Correcting prediction for move {}".format(self,
                                                             correction_tick))

        # State call-backs
        apply_move = self.apply_move
        update_physics = partial(PhysicsSingleUpdateSignal.invoke,
                                 1 / WorldInfo.tick_rate, target=self.pawn)

        # Iterate over all later moves and re-apply them
        for move in self.pending_moves.values():
            # Apply move inputs
            apply_move(move)
            # Update Physics world
            update_physics()

    @requires_netmode(Netmodes.client)
    def client_fire(self):
        self.pawn.weapon_attachment.play_fire_effects()
        self.hear_sound(self.weapon.shoot_sound, self.pawn.position)
        self.weapon.fire(self.camera)

    def client_nudge_clock(self,
               difference:TypeFlag(int, max_value=WorldInfo._MAXIMUM_TICK),
               forward: TypeFlag(bool)) -> Netmodes.client:
        # Update clock
        WorldInfo.elapsed += (difference if forward else -difference) / WorldInfo.tick_rate

        # Reply received correction
        self.server_remove_buffered_lock(WorldInfo.tick, "clock_synch")

    def client_reply_ping(self,
              tick: TypeFlag(int, max_value=WorldInfo._MAXIMUM_TICK)) -> Netmodes.client:
        self.server_deduce_ping(tick)

    @requires_netmode(Netmodes.client)
    def client_send_move(self):
        # Get move information
        current_tick = WorldInfo.tick
        try:
            move = self.pending_moves[current_tick]
        except KeyError:
            return

        # Post physics state copying
        move.position = self.pawn.position
        move.rotation = self.pawn.rotation

        # Check move
        self.server_store_move(move)

    @staticmethod
    def create_movement_struct(*fields):
        attributes = {}

        MAXIMUM_TICK = WorldInfo._MAXIMUM_TICK

        attributes['input_fields'] = fields
        attributes['inputs'] = Attribute(type_of=InputManager, fields=fields)
        attributes['mouse_x'] = Attribute(0.0)
        attributes['mouse_y'] = Attribute(0.0)
        attributes['position'] = Attribute(type_of=Vector)
        attributes['rotation'] = Attribute(type_of=Euler)
        attributes['tick'] = Attribute(type_of=int, max_value=MAXIMUM_TICK)

        attributes['__slots__'] = Struct.__slots__.copy()

        return type("MovementStruct", (Struct,), attributes)

    @requires_netmode(Netmodes.client)
    def destroy_microphone(self):
        del self.microphone
        for key in list(self.sound_channels):
            del self.sound_channels[key]

    def get_clock_correction(self, current_tick, command_tick):
        tick_delta = current_tick - command_tick
        time_delta = int(tick_delta * self.clock_convergence_factor)
        return time_delta

    def get_corrected_state(self, move):
        '''Finds difference between local state and remote state

        :param position: position of state
        :param rotation: rotation of state
        :returns: None if state is within safe limits else correction'''
        pos_difference = self.pawn.position - move.position
        rot_difference = (move.rotation[-1] - self.pawn.rotation[-1]) ** 2
        rot_difference = min(rot_difference, (4 * pi ** 2) - rot_difference)

        if not (pos_difference.length_squared > self.max_position_difference_squared) or \
            (rot_difference > self.max_rotation_difference_squared):
            return

        # Create correction if neccessary
        correction = RigidBodyState()
        PhysicsCopyState.invoke(self.pawn, correction)

        return correction

    @classmethod
    @requires_netmode(Netmodes.client)
    def get_local_controller(cls):
        try:
            return WorldInfo.subclass_of(cls)[0]
        except IndexError:
            return None

    def hear_sound(self, sound_path: TypeFlag(str),
                   source: TypeFlag(Vector)) -> Netmodes.client:
        if not (self.pawn and self.camera):
            return

        intensity = square_falloff(source, self.pawn.position,
                                   self.hear_range, self.effective_hear_range)
        return
        factory = Factory(sound_path)
        return Device().play(factory)

    def hear_voice(self,
                   info: TypeFlag(Replicable),
                   data: TypeFlag(bytes, max_length=MAX_32BIT_INT)) -> Netmodes.client:
        player = self.sound_channels[info]
        player.decode(data)

    def is_locked(self, name):
        return name in self.locks

    def load_keybindings(self):
        '''Read config file for keyboard inputs
        Looks for config file with "ClassName.conf" in config filepath

        :returns: keybindings'''
        class_name = self.__class__.__name__
        assert self.movement_struct, \
            "Movement Struct was not specified for {}".format(self.__class__)

        bindings = load_keybindings(self.config_filepath,
                                    class_name,
                                    self.movement_struct.input_fields)

        print("Loaded {} keybindings for {}".format(len(bindings), class_name))

        return bindings

    def on_initialised(self):
        super().on_initialised()

        self.pending_moves = OrderedDict()

        self.mouse_smoothing = 0.6
        self._mouse_delta = None
        self._mouse_epsilon = 0.001

        self.behaviour = BehaviourTree(self,
                              default={"controller": self})

        self.locks = set()
        self.buffered_locks = FactoryDict(dict,
                                          dict_type=OrderedDict,
                                          provide_key=False)

        self.buffer = deque()

        self.clock_convergence_factor = 1.0
        self.maximum_clock_ahead = int(0.05 * WorldInfo.tick_rate)

        self.ping_influence_factor = 0.8
        self.ping_timer = Timer(1.0, repeat=True)
        self.ping_timer.on_target = self.calculate_ping

        self.setup_input()
        self.setup_microphone()

    def on_notify(self, name):
        if name == "pawn":
            # Register as child for signals
            self.on_pawn_updated()

        elif name == "camera":
            self.on_camera_updated()
            self.camera.active = True

        else:
            super().on_notify(name)

    def on_pawn_updated(self):
        super().on_pawn_updated()

        self.behaviour.reset()

    def on_unregistered(self):
        super().on_unregistered()
        self.destroy_microphone()

    @PlayerInputSignal.global_listener
    def player_update(self, delta_time):
        '''Update function for client instance'''
        if not (self.pawn and self.camera):
            return

        # Get input data
        mouse_diff_x, mouse_diff_y = self.mouse_delta
        current_tick = WorldInfo.tick

        # Create movement
        latest_move = self.movement_struct()

        # Populate move
        latest_move.tick = current_tick
        latest_move.inputs = self.inputs.copy()
        latest_move.mouse_x = mouse_diff_x
        latest_move.mouse_y = mouse_diff_y

        # Apply move inputs
        self.apply_move(latest_move)

        # Remember move for corrections
        self.pending_moves[current_tick] = latest_move

        self.broadcast_voice()

    @PostPhysicsSignal.global_listener
    def post_physics(self):
        '''Post move to server and receive corrections'''
        self.client_send_move()
        self.server_check_move()

    def receive_broadcast(self, message_string: TypeFlag(str)) -> Netmodes.client:
        ReceiveMessage.invoke(message_string)

    def send_voice_server(self,
              data: TypeFlag(bytes, max_length=MAX_32BIT_INT)) -> Netmodes.server:
        info = self.info
        for controller in WorldInfo.subclass_of(Controller):
            if controller is self:
                continue

            controller.hear_voice(info, data)

    def server_add_buffered_lock(self,
            tick: TypeFlag(int, max_value=WorldInfo._MAXIMUM_TICK),
            name: TypeFlag(str)) -> Netmodes.server:
        '''Add a server lock with respect for the dejittering latency'''
        self.buffered_locks[tick][name] = True

    def server_add_lock(self, name: TypeFlag(str)) -> Netmodes.server:
        '''Flag a variable as locked on the server'''
        self.locks.add(name)

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
            latest_move = self.pending_moves[current_tick]

        except KeyError:
            return

        correction = self.get_corrected_state(latest_move)

        # It was a valid move
        if correction is None:
            self.client_acknowledge_move(current_tick)

        # Send the correction
        else:
            self.server_add_lock("correction")
            self.client_apply_correction(current_tick, correction)

    def server_deduce_ping(self,
           tick: TypeFlag(int, max_value=WorldInfo._MAXIMUM_TICK)) -> Netmodes.server:
        '''Callback to determine ping for a client
        Called by client_reply_ping(tick)
        Unlocks the ping synchronisation lock

        :param tick: tick from client reply replicated function'''
        tick_delta = (WorldInfo.tick - tick)
        round_trip_time = tick_delta / WorldInfo.tick_rate

        self.info.ping = lerp(self.info.ping, round_trip_time,
                                            self.ping_influence_factor)
        self.server_remove_lock("ping")

    @requires_netmode(Netmodes.server)
    def server_fire(self):
        print("Rolling back by {:.3f} seconds".format(self.info.ping))

        if 0:
            latency_ticks = WorldInfo.to_ticks(self.info.ping) + 1
            PhysicsRewindSignal.invoke(WorldInfo.tick - latency_ticks)

        super().server_fire()

        if 0:
            PhysicsRewindSignal.invoke()

    def server_remove_buffered_lock(self,
            tick: TypeFlag(int, max_value=WorldInfo._MAXIMUM_TICK),
            name: TypeFlag(str)) -> Netmodes.server:
        '''Remove a server lock with respect for the dejittering latency'''
        self.buffered_locks[tick][name] = False

    def server_remove_lock(self, name: TypeFlag(str)) -> Netmodes.server:
        '''Flag a variable as unlocked on the server'''
        try:
            self.locks.remove(name)

        except KeyError as err:
            raise FlagLockingError("{} was not locked".format(name))\
                 from err

    def server_store_move(self, move: TypeFlag(type_=MarkAttribute("movement_struct"))) -> Netmodes.server:
        '''Store a client move for later processing and clock validation'''

        current_tick = WorldInfo.tick
        target_tick = self.maximum_clock_ahead + current_tick
        move_tick = move.tick

        # If the move is too early, correct clock
        if move_tick > target_tick:
            self.update_buffered_locks(move_tick)
            self.start_clock_correction(target_tick, move_tick)
            return

        self.buffer.append(move)

    @requires_netmode(Netmodes.client)
    def setup_input(self):
        '''Create the input manager for the client'''
        keybindings = self.load_keybindings()

        self.inputs = InputManager(keybindings, BGEInputStatusLookup())
        print("Created input manager")

    @requires_netmode(Netmodes.client)
    def setup_microphone(self):
        '''Create the microphone for the client'''
        self.microphone = MicrophoneStream()
        self.sound_channels = defaultdict(SpeakerStream)

    def set_name(self, name: TypeFlag(str)) -> Netmodes.server:
        self.info.name = name

    def start_clock_correction(self, current_tick, command_tick):
        '''Initiate client clock correction'''
        if not self.is_locked("clock_synch"):
            tick_difference = self.get_clock_correction(current_tick,
                                                        command_tick)
            self.client_nudge_clock(abs(tick_difference),
                                    forward=current_tick > command_tick)
            self.server_add_lock("clock_synch")

    def start_fire(self):
        if not self.weapon:
            return

        if not self.weapon.can_fire or not self.camera:
            return

        self.server_fire()
        self.client_fire()

    @requires_netmode(Netmodes.server)
    @UpdateSignal.global_listener
    def update(self, delta_time):
        '''Validate client clock and apply moves'''
        # Aim ahead by the jitter buffer size
        current_tick = WorldInfo.tick
        target_tick = self.maximum_clock_ahead + current_tick
        consume_move = self.buffer.popleft

        try:
            buffered_move = self.buffer[0]

        except IndexError:
            return

        move_tick = buffered_move.tick

        # Process any buffered locks
        self.update_buffered_locks(move_tick)

        # The tick is late, try and run a newer command
        if move_tick < current_tick:
            # Ensure we check through to the latest tick
            consume_move()

            if self.buffer:
                self.update(delta_time)

            else:
                self.start_clock_correction(target_tick, move_tick)

        # If the tick is early, wait for it to become valid
        elif move_tick > current_tick:
            return

        # Else run the move at the present time (it's valid)
        else:
            consume_move()

            if not (self.pawn and self.camera):
                return

            # Apply move inputs
            self.apply_move(buffered_move)

            # Save expected move results
            self.pending_moves[current_tick] = buffered_move

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

