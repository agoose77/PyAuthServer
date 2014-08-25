from collections import defaultdict, OrderedDict
from functools import partial
from math import pi

from network.decorators import requires_netmode
from network.descriptors import Attribute, MarkAttribute
from network.enums import Netmodes, Roles, IterableCompressionType
from network.iterators import take_single
from network.logger import logger
from network.network_struct import Struct
from network.replicable import Replicable
from network.signals import LatencyUpdatedSignal
from network.type_flag import TypeFlag
from network.world_info import WorldInfo


from .ai.behaviour_tree import BehaviourTree
from .audio import AudioManager
from .configuration import load_keybindings
from .constants import MAX_32BIT_INT
from .coordinates import Vector, Euler
from .enums import *
from .inputs import InputManager, MouseManager
from .jitter_buffer import JitterBuffer
from .network_locks import NetworkLocksMixin
from .resources import ResourceManager
from .signals import *
from .stream import MicrophoneStream, SpeakerStream
from .structs import RigidBodyState


__all__ = ['Controller', 'PlayerController', 'AIController']

TICK_FLAG = TypeFlag(int, max_value=WorldInfo._MAXIMUM_TICK)


class Controller(Replicable):

    roles = Attribute(Roles(Roles.authority, Roles.autonomous_proxy))
    pawn = Attribute(type_of=Replicable, complain=True, notify=True)
    camera = Attribute(type_of=Replicable, complain=True, notify=True)
    weapon = Attribute(type_of=Replicable, complain=True, notify=True)
    info = Attribute(type_of=Replicable, complain=True)

    def attach_camera(self, camera):
        """Connects camera to pawn

        :param camera: camera instance
        """
        self._camera = camera

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

    def on_camera_replicated(self, camera):
        """Called when camera attribute is replicated

        :param camera: camera attribute
        """
        if camera:
            self.attach_camera(camera)
            camera.active = True

        else:
            self.remove_camera()

    def on_initialised(self):
        super().on_initialised()

        self.hear_range = 15
        self.effective_hear_range = 10
        self.replication_priority = 2.0

        self._camera = None
        self._pawn = None

    def on_pawn_replicated(self, pawn):
        if pawn:
            self.register_listener_to_pawn(pawn)

        else:
            self.unregister_listener_to_pawn()

    def on_unregistered(self):
        # Remove player pawn
        self.forget_pawn()

        # The player is gone, remove info
        if self.info:
            self.info.request_unregistration()

        super().on_unregistered()

    @requires_netmode(Netmodes.server)
    def possess(self, replicable):
        self.pawn = replicable
        self.pawn.possessed_by(self)

        # Setup lookups
        self.info.pawn = replicable
        self.pawn.info = self.info

        self.register_listener_to_pawn(replicable)

    def register_listener_to_pawn(self, pawn):
        """Registers as listener for pawn events

        :param pawn: pawn instance
        """
        self._pawn = pawn
        pawn.register_child(self, greedy=True)

    def remove_camera(self):
        """Disconnects camera from pawn"""
        self._camera.remove_parent()
        self._camera = None

    def forget_pawn(self):
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

    @requires_netmode(Netmodes.server)
    def server_fire(self):
        self.weapon.fire(self.camera)

        # Update flash count (for client-side fire effects)
        self.pawn.flash_count += 1
        if self.pawn.flash_count > 255:
            self.pawn.flash_count = 0

        weapon_sound = self.weapon.resources['sounds'][self.weapon.shoot_sound]

        for controller in WorldInfo.subclass_of(Controller):
            if controller == self:
                continue

            continue
            controller.hear_sound(weapon_sound, self.pawn.world_position, self.pawn.world_rotation,
                                  self.pawn.world_velocity)

    @requires_netmode(Netmodes.server)
    def set_camera(self, camera):
        self.camera = camera
        self.camera.possessed_by(self)

        self.attach_camera(camera)

    @requires_netmode(Netmodes.server)
    def set_weapon(self, weapon):
        self.weapon = weapon
        self.weapon.possessed_by(self)
        self.pawn.weapon_attachment_class = weapon.attachment_class

    @requires_netmode(Netmodes.server)
    def unpossess(self):
        self.unregister_listener_to_pawn()

        self.info.pawn = None
        self.pawn.info = None

        self.pawn.unpossessed()
        self.pawn = None

    def unregister_listener_to_pawn(self):
        """Unregister as listener for pawn events"""
        self._pawn.unregister_child(self, greedy=True)
        self._pawn = None


class AIController(Controller):

    def get_visible(self, ignore_self=True):
        if not self.camera:
            return

        sees = self.camera.sees_actor
        my_pawn = self.pawn

        for actor in WorldInfo.subclass_of(Pawn):
            if actor == my_pawn and ignore_self:
                continue

            elif sees(actor):
                return actor

    def unpossess(self):
        self.behaviour.reset()
        self.behaviour.blackboard['controller'] = self

        super().unpossess()

    def hear_sound(self, sound_path, position, rotation, velocity):
        return

    def on_initialised(self):
        super().on_initialised()

        self.camera_mode = CameraMode.first_person
        self.behaviour = BehaviourTree(self)
        self.behaviour.blackboard['controller'] = self

    @LogicUpdateSignal.global_listener
    def update(self, delta_time):
        self.behaviour.update()


class PlayerController(Controller, NetworkLocksMixin):
    """Player pawn controller network object"""

    movement_struct = None
    missing_movement_struct = None

    maximum_squared_position_error = 1.2
    maximum_rotation_error = ((2 * pi) / 100)
    additional_move_buffering_latency = 0.1

    def apply_move(self, move):
        """Apply move contents to Controller state

        :param move: move to process
        """
        blackboard = self.behaviour.blackboard

        blackboard['inputs'] = move.inputs
        blackboard['mouse'] = move.mouse_x, move.mouse_y

        self.behaviour.update()

    def client_acknowledge_move(self, move_id: TICK_FLAG) -> Netmodes.client:
        """Remove move and previous moves from waiting corrections buffer

        :param move_id: ID of valid move
        :returns: result of acknowledgement attempt
        """
        if not self.pawn:
            logger.warning("Could not find Pawn for {} in order to acknowledge a move".format(self))
            return False

        remove_move = self.pending_moves.pop

        try:
            remove_move(move_id)

        except KeyError:
            # We don't mind if we've handled it already
            if self.pending_moves and move_id < take_single(self.pending_moves):
                return False

            logger.warning("Couldn't find move to acknowledge for move {}".format(move_id))
            return False

        # Remove any older moves
        older_moves = [k for k in self.pending_moves if k < move_id]

        for move_id in older_moves:
            remove_move(move_id)

        return True

    def client_apply_correction(self, move_id: TICK_FLAG, correction: TypeFlag(RigidBodyState)) -> Netmodes.client:
        """Apply a correction to a stored move and replay successive inputs to update client stat

        :param move_id: ID of invalid move
        :param correction: RigidBodyState struct instance
        """

        # Remove the lock at this network tick on server
        self.server_remove_buffered_lock(self.current_move.id + 1, "correction")

        if not self.pawn:
            logger.warning("Could not find Pawn for {} in order to correct a move".format(self))
            return

        if not self.client_acknowledge_move(move_id):
            return

        CopyStateToActor.invoke(correction, self.pawn)
        logger.info("{}: Correcting prediction for move {}".format(self, move_id))

        # State call-backs
        apply_move = self.apply_move
        update_physics = partial(PhysicsSingleUpdateSignal.invoke, 1 / WorldInfo.tick_rate, target=self.pawn)

        # Iterate over all later moves and re-apply them
        for move in self.pending_moves.values():
            # Apply move inputs
            apply_move(move)
            # Update Physics world
            update_physics()

    @requires_netmode(Netmodes.client)
    def client_fire(self):
        self.pawn.weapon_attachment.play_fire_effects()

        weapon_sounds = self.weapon.resources['sounds']
        shoot_sound = weapon_sounds[self.weapon.shoot_sound]
        # TODO: enable this for release
     #   self.hear_sound(shoot_sound, self.pawn.world_position, self.pawn.world_rotation, self.pawn.world_velocity)
        self.weapon.fire(self.camera)

    @requires_netmode(Netmodes.client)
    def client_setup_input(self):
        """Create the input manager for the client"""
        keybindings = self.load_keybindings()

        self.inputs = InputManager(keybindings)
        self.mouse = MouseManager(interpolation=0.6)
        self.move_history = self.missing_movement_struct()

        logger.info("Created User Input Managers")

    @requires_netmode(Netmodes.client)
    def client_setup_sound(self):
        """Create the microphone for the client"""
        self.audio = AudioManager()
        self.voice_microphone = MicrophoneStream()
        self.voice_channels = defaultdict(SpeakerStream)

    @requires_netmode(Netmodes.client)
    def client_send_move(self):
        """Sends a Move to the server for simulation"""

        move = self.current_move
        move_history = self.move_history

        if not self.pawn:
            return

        # Log an error if we should be able to send a move
        if move is None:
            logger.error("No move could be sent to the server for tick {}!".format(WorldInfo.tick))
            return

        # Post physics state copying
        move.position = self.pawn.world_position.copy()
        move.rotation = self.pawn.world_rotation.copy()

        # Check move
        self.server_store_move(move, move_history)

        # Post checking move
        move_history.append(move)

    @requires_netmode(Netmodes.client)
    def client_send_voice(self):
        """Dump voice information and encode it for the server"""
        data = self.voice_microphone.encode()

        if data:
            self.server_receive_voice(data)

    @staticmethod
    def create_missing_moves_struct(move_cls, history_length):
        """Create a Struct with valid fields for use as a Move History record

        :param move_cls: class used to store moves
        :param history_length: number of moves to store
        :rtype: Struct
        """
        attributes = {}

        MAXIMUM_TICK = WorldInfo._MAXIMUM_TICK

        field_compression = IterableCompressionType.compress

        for input_name in move_cls.input_fields:
            attributes["{}_list".format(input_name)] = Attribute(type_of=list, element_flag=TypeFlag(bool),
                                                                 compression=field_compression)
        attributes['mouse_x_list'] = Attribute(type_of=list, element_flag=TypeFlag(float),
                                               compression=field_compression)
        attributes['mouse_y_list'] = Attribute(type_of=list, element_flag=TypeFlag(float),
                                               compression=field_compression)
        attributes['id_start'] = Attribute(type_of=int, max_value=MAXIMUM_TICK)
        attributes['id_end'] = Attribute(type_of=int, max_value=MAXIMUM_TICK)
        attributes['__slots__'] = tuple(Struct.__slots__)

        # Local variables
        list_names = ["{}_list".format(n) for n in move_cls.input_fields]
        all_list_names = list_names + ["mouse_x_list", "mouse_y_list"]
        keybinding_index_map = OrderedDict((name, index) for index, name in enumerate(move_cls.input_fields))

        # Methods
        def append(move_history, move):
            if move_history.id_start is None:
                move_history.id_start = move_history.id_end = move.id

            if (move.id - move_history.id_end) > 1:
                raise ValueError("Move discontinuity between last move and appended move")

            # Add input fields
            for list_name, field_name in zip(list_names, move.input_fields):
                field = getattr(move_history, list_name)
                if field is None:
                    field = []
                    setattr(move_history, list_name, field)
                field.append(getattr(move.inputs, field_name))

            # Add other fields
            if move_history.mouse_x_list is None:
                move_history.mouse_x_list = []

            if move_history.mouse_y_list is None:
                move_history.mouse_y_list = []

            move_history.mouse_x_list.append(move.mouse_x)
            move_history.mouse_y_list.append(move.mouse_y)
            move_history.id_end = move.id

            # Enforce upper limit
            if len(move_history) > history_length:
                move_history.popleft()

        def clear(move_history):
            """Clear all fields for history struct"""
            for list_name in all_list_names:
                getattr(move_history, list_name).clear()

            move_history.id_start = move_history.id_end = None

        def popleft(move_history):
            for list_name in all_list_names:
                getattr(move_history, list_name).pop(0)

            move_history.id_start += 1

        def __bool__(self):
            return bool(len(self))

        def __contains__(move_history, index):
            if not move_history:
                return False

            return move_history.id_start <= index <= move_history.id_end

        def __getitem__(move_history, index):
            if isinstance(index, slice):
                start = move_history.id_start
                length = len(move_history)
                indices = range(*index.indices(start + length))
                return [move_history[i] for i in indices if i >= start]

            if index < 0:
                index += (move_history.id_end or -2) + 1

            if not index in range(move_history.id_start, move_history.id_end + 1):
                raise IndexError("Move not in history")

            offset = index - move_history.id_start
            values = [getattr(move_history, list_name)[offset] for list_name in list_names]

            move = move_cls()
            move.inputs = InputManager(keybinding_index_map, status_lookup=values.__getitem__)
            move.mouse_x = move_history.mouse_x_list[offset]
            move.mouse_y = move_history.mouse_y_list[offset]
            move.id = index

            return move

        def __iter__(move_history):
            for move_id in range(len(move_history)):
                yield move_history[move_id]

        def __len__(move_history):
            if not move_history.mouse_x_list:
                return 0

            return (move_history.id_end - move_history.id_start) + 1

        attributes['append'] = append
        attributes['clear'] = clear
        attributes['popleft'] = popleft

        attributes['__getitem__'] = __getitem__
        attributes['__iter__'] = __iter__
        attributes['__len__'] = __len__
        attributes['__contains__'] = __contains__

        return type("MovementHistoryStruct", (Struct,), attributes)

    @staticmethod
    def create_movement_struct(*fields):
        """Create a Struct with valid fields for use as a Move record

        :param *fields: named, ordered input fields
        :rtype: Struct
        """
        attributes = {}

        MAXIMUM_TICK = WorldInfo._MAXIMUM_TICK

        attributes['input_fields'] = fields
        attributes['inputs'] = Attribute(type_of=InputManager, fields=fields)
        attributes['mouse_x'] = Attribute(0.0, max_precision=True)
        attributes['mouse_y'] = Attribute(0.0, max_precision=True)
        attributes['position'] = Attribute(type_of=Vector)
        attributes['rotation'] = Attribute(type_of=Euler)
        attributes['id'] = Attribute(type_of=int, max_value=MAXIMUM_TICK)

        attributes['__slots__'] = tuple(Struct.__slots__)

        return type("MovementStruct", (Struct,), attributes)

    @requires_netmode(Netmodes.client)
    def destroy_microphone(self):

        del self.voice_microphone
        for key in list(self.voice_channels):
            del self.voice_channels[key]

    @requires_netmode(Netmodes.server)
    def get_corrected_state(self, move):
        """Finds difference between local state and remote state

        :param move: move result from client
        :returns: None if state is valid else correction
        """

        if move.position is None or move.rotation is None:
            return None

        pos_difference = self.pawn.world_position - move.position
        rot_difference = min(abs(self.pawn.world_rotation[-1] - move.rotation[-1]), 2 * pi)

        position_invalid = (pos_difference.length_squared > self.maximum_squared_position_error)
        rotation_invalid = (rot_difference > self.maximum_rotation_error)

        if not (position_invalid or rotation_invalid):
            return

        # Create correction if necessary
        correction = RigidBodyState()
        CopyActorToState.invoke(self.pawn, correction)

        return correction

    @staticmethod
    @requires_netmode(Netmodes.client)
    def get_local_controller():
        """Get the local PlayerController instance opn the client"""
        return take_single(WorldInfo.subclass_of(PlayerController))

    def hear_sound(self, resource: TypeFlag(str), position: TypeFlag(Vector), rotation: TypeFlag(Euler),
                   velocity: TypeFlag(Vector)) -> Netmodes.client:
        """Play a sound resource on the client

        :param resource: relative resource path
        :param position: position of sound source
        :param rotation: rotation of sound source
        :param velocity: velocity of sound source
        """
        if not (self.pawn and self.camera):
            return

        sound_path = ResourceManager.from_relative_path(resource)
        handle = self.audio.play_sound(sound_path)

        source_to_pawn = (self.pawn.world_position - position).normalized()
        forward = Vector((0, 1, 0))

        handle.location = position
        handle.velocity = velocity
        handle.orientation = forward.rotation_difference(source_to_pawn)

    def hear_voice(self, info: TypeFlag(Replicable), data: TypeFlag(bytes, max_length=MAX_32BIT_INT))-> Netmodes.client:
        """Play voice data from a remote client for another client

        :param info: ReplicationInfo of source PlayerController
        :param data: voice data
        """
        player = self.voice_channels[info]
        player.decode(data)

    def load_keybindings(self):
        """Read config file for keyboard inputs
        Looks for config file with "ClassName.conf" in config filepath

        :returns: keybindings"""
        class_name = self.__class__.__name__

        # Get the input fields
        try:
            input_fields = self.movement_struct.input_fields

        except AttributeError as err:
            raise AttributeError("Move Struct was not defined for {}".format(self.__class__)) from err

        # Convert input codes to strings
        input_codes = {k: str(v) for k, v in InputEvents.keys_to_values.items()}
        keymap_relative_path = ResourceManager["configuration"]["keymaps"]["inputs.conf"]
        keymap_absolute_path = ResourceManager.from_relative_path(keymap_relative_path)

        bindings = load_keybindings(keymap_absolute_path, class_name, input_fields, input_codes)
        logger.info("Loaded {} key-bindings for {}".format(len(bindings), class_name))
        return bindings

    def on_initialised(self):
        super().on_initialised()

        self.pending_moves = OrderedDict()
        self.current_move = None
        self.previous_move = None

        self.behaviour = BehaviourTree(self, default={"controller": self})

        # Permit move recovery by sending a history
        self.move_history_dict = {}
        self.move_history_base = None

        # Number of moves to buffer
        buffer_length = WorldInfo.to_ticks(self.__class__.additional_move_buffering_latency)

        # Queued moves
        self.buffered_moves = JitterBuffer(int(buffer_length * 1.5), buffer_length,
                                           on_discontinuity=self.recover_missing_moves)

        self.client_setup_input()
        self.client_setup_sound()

    def on_notify(self, name):
        if name == "pawn":
            # Register as child for signals
            self.on_pawn_replicated(self.pawn)

        elif name == "camera":
            self.on_camera_replicated(self.camera)

        else:
            super().on_notify(name)

    def on_pawn_updated(self):
        super().on_pawn_updated()

        self.behaviour.reset()

    @LatencyUpdatedSignal.listener
    @requires_netmode(Netmodes.server)
    def on_ping_estimate_updated(self, ping_estimate):
        self.info.ping = ping_estimate

    def on_unregistered(self):
        super().on_unregistered()

        self.destroy_microphone()

    @PlayerInputSignal.global_listener
    def player_update(self, delta_time):
        """Update function for client-side controller instance

        :param delta_time: elapsed time since last update
        """
        if not (self.pawn and self.camera):
            return

        # Update audio
        self.audio.listener_location = self.pawn.world_position
        self.audio.listener_velocity = self.pawn.world_velocity
        self.audio.listener_orientation = self.pawn.world_rotation.to_quaternion()
        self.audio.distance_model = AudioDistanceModel.linear

        self.mouse.update()

        # Get input data
        mouse_diff_x, mouse_diff_y = self.mouse.delta_position

        # Create movement
        latest_move = self.movement_struct()

        # Populate move
        latest_move.id = (self.current_move.id + 1) if self.current_move else 0
        latest_move.inputs = self.inputs.copy()
        latest_move.mouse_x = mouse_diff_x
        latest_move.mouse_y = mouse_diff_y

        # Apply move inputs
        self.apply_move(latest_move)

        # Remember move for corrections
        self.pending_moves[latest_move.id] = latest_move

        self.previous_move = self.current_move
        self.current_move = latest_move

        self.client_send_voice()

    @PostPhysicsSignal.global_listener
    def post_physics(self):
        """Post-physics callback to send move to server and receive corrections"""
        self.client_send_move()
        self.server_check_move()

    def receive_broadcast(self, message_string: TypeFlag(str)) -> Netmodes.client:
        """Message handler for PlayerController, invokes a ReceiveMessage signal

        :param message_string: message from server
        """
        ReceiveMessage.invoke(message_string)

    def recover_missing_moves(self, previous_id, next_id):
        """Jitter buffer callback to find missing moves using move history

        :param move: next move
        :param previous_move: last valid move
        """
        required_ids = list(range(previous_id + 1, next_id))
        recovered_moves = []

        # Search every move history to find missing moves!
        for move in self.move_history_dict.values():
            for required_id in required_ids:
                if required_id in move:
                    recovered_moves.append(move[required_id])
                    required_ids.remove(required_id)

        return recovered_moves

    def server_receive_voice(self, data: TypeFlag(bytes, max_length=MAX_32BIT_INT)) -> Netmodes.server:
        """Send voice information to the server

        :param data: voice data
        """
        info = self.info
        for controller in WorldInfo.subclass_of(Controller):
            if controller is self:
                continue

            controller.hear_voice(info, data)

    @requires_netmode(Netmodes.server)
    def server_check_move(self):
        """Check result of movement operation following Physics update"""
        # Get move information
        current_move = self.current_move

        # We are forced to acknowledge moves whose base we've already corrected
        if self.is_locked("correction"):
            return

        # Validate move
        if current_move is None:
            return

        correction = self.get_corrected_state(current_move)

        if current_move.inputs.debug:
            correction = RigidBodyState()
            CopyActorToState.invoke(self.pawn, correction)

        # It was a valid move
        if correction is None:
            self.client_acknowledge_move(current_move.id)

        # Send the correction
        else:
            self.server_add_lock("correction")
            self.client_apply_correction(current_move.id, correction)

    def server_cull_excess_history(self, oldest_id):
        """Remove movement history that is older than our buffer

        :param oldest_id: oldest stored move ID
        """
        # Search from current oldest history to oldest move
        for search_id in range(self.move_history_base, oldest_id):
            if not search_id in self.move_history_dict:
                continue

            history = self.move_history_dict.pop(search_id)
            self.move_history_base = history.id_end

    @requires_netmode(Netmodes.server)
    def server_fire(self):
        logger.info("Rolling back by {:.3f} seconds".format(self.info.ping))

        if True:
            latency_ticks = WorldInfo.to_ticks(self.info.ping) + 1
            physics_callback = super().server_fire
            PhysicsRewindSignal.invoke(physics_callback, WorldInfo.tick - latency_ticks)

        else:
            super().server_fire()

    def server_store_move(self, move: TypeFlag(type_=MarkAttribute("movement_struct")),
                          previous_moves: TypeFlag(type_=MarkAttribute("missing_movement_struct"))) -> Netmodes.server:
        """Store a client move for later processing and clock validation"""

        # Store move
        self.buffered_moves.insert(move.id, move)

        # Could optimise using an increment and try-pop
        if previous_moves is None:
            return

        self.move_history_dict[move.id] = previous_moves

        if self.move_history_base is None:
            self.move_history_base = move.id

        else:
            oldest_id, _ = self.buffered_moves[0]

            if self.move_history_base < oldest_id:
                self.server_cull_excess_history(oldest_id)

    def server_set_name(self, name: TypeFlag(str)) -> Netmodes.server:
        """Renames the Player on the server

        :param name: new name to assign to Player
        """
        self.info.name = name

    def start_fire(self):
        if not self.weapon:
            return

        if not self.weapon.can_fire or not self.camera:
            return

        self.server_fire()
        self.client_fire()

    @requires_netmode(Netmodes.server)
    @LogicUpdateSignal.global_listener
    def update(self, delta_time):
        """Validate client clock and apply moves

        :param delta_time: elapsed time since last update
        """

        try:
            move_id, buffered_move = self.buffered_moves.popitem()

        except ValueError:
            logger.exception("No move was received from {} in time for tick {}!".format(self, WorldInfo.tick))
            return

        if not self.pawn:
            return

        # Process any buffered locks
        self.update_buffered_locks(move_id)

        # Ensure we can update our simulation
        if not self.camera:
            return

        # Apply move inputs
        self.apply_move(buffered_move)

        # Save expected move results
        self.pending_moves[move_id] = buffered_move
        self.current_move = buffered_move

