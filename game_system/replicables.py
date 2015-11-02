from network.replicable import Replicable
from network.replication import Serialisable, Pointer
from network.type_serialisers import TypeInfo
from network.enums import Roles, Netmodes
from network.annotations.decorators import reliable, requires_netmode

from .coordinates import Vector
from .entity import Actor
from .enums import InputButtons
from .latency_compensation import JitterBuffer

from collections import OrderedDict, deque
from logging import getLogger
from math import radians, pi
from os import path
from time import time


class PawnController(Replicable):
    """Base class for Pawn controllers"""

    roles = Serialisable(Roles(Roles.authority, Roles.autonomous_proxy))
    pawn = Serialisable(data_type=Replicable, notify_on_replicated=True)
    info = Serialisable(data_type=Replicable)

    def __init__(self, scene, unique_id, is_static=False):
        super().__init__(scene, unique_id, is_static)

        self.logger = getLogger(repr(self))

    def can_replicate(self, is_owner, is_initial):
        yield from super().can_replicate(is_owner, is_initial)

        yield "pawn"
        yield "info"

    def on_replicated(self, name):
        if name == "pawn":
            self.on_take_control(self.pawn)

    def on_destroyed(self):
        if self.pawn is not None:
            self.scene.remove_replicable(self.pawn)

        super().on_destroyed()

    def take_control(self, pawn):
        """Take control of pawn

        :param pawn: Pawn instance
        """
        if pawn is self.pawn:
            return

        self.pawn = pawn
        self.on_take_control(self.pawn)

    def release_control(self):
        """Release control of possessed pawn"""
        self.pawn.released_control()
        self.pawn = None

    def on_take_control(self, pawn):
        pawn.controlled_by(self)


class PlayerPawnController(PawnController):
    """Base class for player pawn controllers"""

    MAX_POSITION_ERROR_SQUARED = 0.5
    MAX_ORIENTATION_ANGLE_ERROR_SQUARED = radians(5) ** 2

    clock = Serialisable(data_type=Replicable)

    # input_context = InputContext()
    # info_cls = PlayerReplicationInfo TODO
    def __init__(self, scene, unique_id, is_static=False):
        """Initialisation method"""
        super().__init__(scene, unique_id, is_static)

        self.initialise_client()
        self.initialise_server()

    def can_replicate(self, is_owner, is_initial):
        yield from super().can_replicate(is_owner, is_initial)

    @reliable
    def client_correct_move(self, move_id: (int, {'max_value': 1000}), position: Vector, yaw: float, velocity: Vector,
                            angular_yaw: float) -> Netmodes.client:
        """Correct previous move which was mis-predicted

        :param move_id: ID of move to correct
        :param position: corrected position
        :param yaw: corrected yaw
        :param velocity: corrected velocity
        :param angular_yaw: corrected angular yaw
        """
        pawn = self.pawn
        if not pawn:
            return

        # Restore pawn state
        pawn.transform.world_position = position
        pawn.physics.world_velocity = velocity

        # Recreate Z rotation
        orientation = pawn.transform.world_orientation
        orientation.z = yaw
        pawn.transform.world_orientation = orientation

        # Recreate Z angular rotation
        angular = pawn.physics.world_angular
        angular.z = angular_yaw
        pawn.physics.world_angular = angular

        process_inputs = self.process_inputs
        sent_states = self.sent_states

        # Correcting move
        self.logger.info("Correcting an invalid move: {}".format(move_id))

        for move_id in range(move_id, self.move_id + 1):
            state = sent_states[move_id]
            buttons, ranges = state.read()

            process_inputs(buttons, ranges)
            # self.scene.physics_manager.update_actor(pawn)

        # Remember this correction, so that older moves are not corrected
        self.latest_correction_id = move_id

    def on_input(self, delta_time, input_manager):
        """Handle local inputs from client
        :param input_manager: input system
        """
        remapped_state = self.input_context.remap_state(input_manager, self.input_map)
        packed_state = self.input_context.network.struct_cls()
        packed_state.write(remapped_state)

        self.move_id += 1
        self.sent_states[self.move_id] = packed_state
        self.recent_states.appendleft(packed_state)

        self.process_inputs(*remapped_state)

    @requires_netmode(Netmodes.client)
    def client_send_move(self):
        """Send inputs, alongside results of applied inputs, to the server"""
        pawn = self.pawn
        if not pawn:
            return

        position = pawn.transform.world_position
        yaw = pawn.transform.world_orientation.z

        self.server_receive_move(self.move_id, self.latest_correction_id, self.recent_states, position, yaw)

    def get_input_map(self):
        """Return keybinding mapping (from actions to buttons)"""
        file_path = path.join(self.__class__.__name__, "input_map.cfg")
        defaults = {k: str(v) for k, v in InputButtons.keys_to_values.items()}
        configuration = self.scene.resource_manager.open_configuration(file_path, defaults=defaults)
        return {name: int(binding) for name, binding in configuration.items() if isinstance(binding, str)}

    @requires_netmode(Netmodes.client)
    def initialise_client(self):
        """Initialise client-specific player controller state"""

        self.input_map = self.get_input_map()
        self.move_id = 0
        self.latest_correction_id = 0

        self.sent_states = OrderedDict()
        self.recent_states = deque(maxlen=5)

    @requires_netmode(Netmodes.server)
    def initialise_server(self):
        """Initialise server-specific player controller state"""
        self.info = self.__class__.info()
        self.info.possessed_by(self)

        # Network jitter compensation
        ticks = round(0.1 * self.scene.world.tick_rate)
        self.buffer = JitterBuffer(length=ticks)

        # Clienat results of simulating moves
        self.client_moves_states = {}

        # ID of move waiting to be verified
        self.pending_validation_move_id = None
        self.last_corrected_move_id = 0

        # TODO destroy this
        self.scene.messenger.add_subscriber("tick", self.on_tick)

    def receive_message(self, message: str, player_info: Replicable) -> Netmodes.client:
        self.scene.messenger.send("message", message=message, player_info=player_info)

    def send_message(self, message: str, info: Replicable=None) -> Netmodes.server:
        self_info = self.info

        # Broadcast to all controllers
        if info is None:
            for replicable in self.scene.replicables.values():
                if not isinstance(replicable, PlayerReplicationInfo):
                    continue

                controller = replicable.owner
                controller.receive_message(message, self_info)

        else:
            controller = info.owner
            controller.receive_message(message, self_info)

    def set_name(self, name: str)->Netmodes.server:
        self.info.name = name

    def update_ping_estimate(self, rtt):
        """Update ReplicationInfo with approximation of connection ping
        :param rtt: round trip time from server to client and back
        """
        self.info.ping = rtt / 2

    def server_receive_move(self, move_id: (int, {'max_value': 1000}), latest_correction_id: (int, {'max_value': 1000}),
                            recent_states: (list, {'element_flag':
                                                       TypeInfo(Pointer("input_context.network.struct_cls"))
                            }),
                            position: Vector, yaw: float) -> Netmodes.server:
        """Handle remote client inputs

        :param move_id: unique ID of move
        :param recent_states: list of recent input states
        """
        push = self.buffer.push

        try:
            for i, state in enumerate(recent_states):
                push(state, move_id - i)

        except KeyError:
            pass

        # Save physics state for this move for later validation
        self.client_moves_states[move_id] = position, yaw, latest_correction_id

    def post_physics(self):
        self.client_send_move()
        self.server_validate_last_move()

    def process_inputs(self, buttons, ranges):
        pass

    @requires_netmode(Netmodes.server)
    def server_validate_last_move(self):
        """Validate result of applied input states.
        Send correction to client if move was invalid.
        """
        # Well, we need a Pawn!
        pawn = self.pawn
        if not pawn:
            return

        # If we don't have a move ID, bail here
        move_id = self.pending_validation_move_id
        if move_id is None:
            return

        # We've handled this
        self.pending_validation_move_id = None

        moves_states = self.client_moves_states

        # Delete old move states
        old_move_ids = [i for i in moves_states if i < move_id]
        for old_move_id in old_move_ids:
            moves_states.pop(old_move_id)

        # Get corrected state
        client_position, client_yaw, client_last_correction = moves_states.pop(move_id)

        # Don't bother checking if we're already checking invalid state
        if client_last_correction < self.last_corrected_move_id:
            return

        # Check predicted position is valid
        position = pawn.transform.world_position
        velocity = pawn.physics.world_velocity
        yaw = pawn.transform.world_orientation.z
        angular_yaw = pawn.physics.world_angular.z

        pos_err = (client_position - position).length_squared > self.__class__.MAX_POSITION_ERROR_SQUARED
        abs_yaw_diff = ((client_yaw - yaw) % pi) ** 2
        rot_err = min(abs_yaw_diff, pi - abs_yaw_diff) > self.__class__.MAX_ORIENTATION_ANGLE_ERROR_SQUARED

        if pos_err or rot_err:
            self.client_correct_move(move_id, position, yaw, velocity, angular_yaw)
            self.last_corrected_move_id = move_id

    @requires_netmode(Netmodes.server)
    def on_tick(self, delta_time):
        try:
            input_state, move_id = next(self.buffer)

        except StopIteration:
            return

        except ValueError as err:
            self.logger.error(err)
            return

        if not self.pawn:
            return

        buttons, ranges = input_state.read()
        self.process_inputs(buttons, ranges)

        self.pending_validation_move_id = move_id


class Pawn(Actor):

    def released_control(self):
        pass

    def controlled_by(self, controller):
        pass