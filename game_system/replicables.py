from network.replicable import Replicable
from network.replication import Serialisable, Pointer
from network.type_serialisers import TypeInfo
from network.annotations.decorators import reliable, requires_netmode, simulated
from network.enums import Netmodes, Roles

from .coordinates import Vector
from .entity import Actor
from .enums import InputButtons
from .input import InputContext
from .latency_compensation import JitterBuffer

from collections import OrderedDict, deque
from logging import getLogger
from math import radians, pi, floor
from os import path
from time import time


class ReplicationInfo(Replicable):
    """Replicated information object for PawnController"""
    pawn = Serialisable(data_type=Replicable)
    roles = Serialisable(Roles(Roles.authority, Roles.simulated_proxy))

    def __init__(self, unique_id, scene, id_is_explicit=False):
        self.always_relevant = True

    def can_replicate(self, is_owner, is_initial):
        yield from super().can_replicate(is_owner, is_initial)

        yield "pawn"


class PlayerReplicationInfo(ReplicationInfo):
    """Replicated information object for PlayerPawnController"""
    name = Serialisable("")
    ping = Serialisable(0.0)

    def can_replicate(self, is_owner, is_initial):
        yield from super().can_replicate(is_owner, is_initial)

        yield "name"
        yield "ping"


class Clock(Replicable):
    roles = Serialisable(Roles(Roles.authority, Roles.autonomous_proxy))

    def __init__(self, scene, unique_id, id_is_explicit=False):
        if scene.world.netmode == Netmodes.server:
            self.initialise_server()
        else:
            self.initialise_client()

    def initialise_client(self):
        self.nudge_minimum = 0.05
        self.nudge_maximum = 0.4
        self.nudge_factor = 0.8

        self.estimated_elapsed_server = 0.0

    def initialise_server(self):
        self.poll_timer = self.scene.add_timer(1.0, repeat=True)
        self.poll_timer.on_elapsed = self.server_send_clock

    def destroy_client(self):
        super().on_destroyed()

    def destroy_server(self):
        self.scene.remove_timer(self.poll_timer)

        super().on_destroyed()

    def server_send_clock(self):
        self.client_update_clock(WorldInfo.elapsed)

    def client_update_clock(self, elapsed: float) -> Netmodes.client:
        controller = self.owner
        if controller is None:
            return

        info = controller.info

        # Find difference between local and remote time
        difference = self.estimated_elapsed_server - (elapsed + info.ping)
        abs_difference = abs(difference)

        if abs_difference < self.nudge_minimum:
            return

        if abs_difference > self.nudge_maximum:
            self.estimated_elapsed_server -= difference

        else:
            self.estimated_elapsed_server -= difference * self.nudge_factor

    def on_destroyed(self):
        if self.scene.world.netmode == Netmodes.server:
            self.destroy_server()

        else:
            self.destroy_client()

    @property
    def tick(self):
        return floor(self.estimated_elapsed_server * self.scene.world.tick_rate)

    @property
    def sync_interval(self):
        return self.poll_timer.delay

    @sync_interval.setter
    def sync_interval(self, delay):
        self.poll_timer.delay = delay

    @simulated
    def on_tick(self):
        self.estimated_elapsed_server += 1 / self.scene.world.tick_rate


class PawnController(Replicable):
    """Base class for Pawn controllers"""

    roles = Serialisable(Roles(Roles.authority, Roles.autonomous_proxy))
    pawn = Serialisable(data_type=Replicable, notify_on_replicated=True)
    info = Serialisable(data_type=Replicable)

    info_class = ReplicationInfo

    def __init__(self, scene, unique_id, id_is_explicit=False):
        self.logger = getLogger(repr(self))

        if scene.world.netmode == Netmodes.server:
            self.info = self.scene.add_replicable(self.info_class)
            print("SET INFO", self.info)

            # When RTT estimate is updated
            self.messenger.add_subscriber("estimated_rtt", self.server_on_rtt_estimate_updated)

        else:
            pass

    def on_destroyed(self):
        if self.scene.world.netmode == Netmodes.server:
            if self.pawn is not None:
                self.scene.remove_replicable(self.pawn)

        super().on_destroyed()

    def server_on_rtt_estimate_updated(self, rtt_estimate):
        self.info.ping = rtt_estimate / 2

    def can_replicate(self, is_owner, is_initial):
        yield from super().can_replicate(is_owner, is_initial)

        yield "pawn"
        yield "info"

    def on_replicated(self, name):
        if name == "pawn":
            self.on_take_control(self.pawn)

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

    clock = Serialisable(data_type=Replicable)

    MAX_POSITION_ERROR_SQUARED = 0.5
    MAX_ORIENTATION_ANGLE_ERROR_SQUARED = radians(5) ** 2

    input_context = InputContext()
    info_class = PlayerReplicationInfo

    def __init__(self, scene, unique_id, id_is_explicit=False):
        """Initialisation method"""
        super().__init__(scene, unique_id, id_is_explicit)

        if scene.world.netmode == Netmodes.server:
            self.info = self.scene.add_replicable(self.info_class)
            #self.info.possessed_by(self)
            print("INFO", self.info)

            # Network jitter compensation
            ticks = round(0.1 * self.scene.world.tick_rate)
            self.buffer = JitterBuffer(length=ticks)

            # Clienat results of simulating moves
            self.client_moves_states = {}

            # ID of move waiting to be verified
            self.pending_validation_move_id = None
            self.last_corrected_move_id = 0

            self.scene.messenger.add_subscriber("tick", self.server_on_tick)
            self.scene.messenger.add_subscriber("post_tick", self.server_validate_last_move)

        else:
            self.input_map = self.get_input_map()
            self.move_id = 0
            self.latest_correction_id = 0

            self.sent_states = OrderedDict()
            self.recent_states = deque(maxlen=5)

            self.scene.world.messenger.add_subscriber("input_updated", self.client_on_input)
            self.scene.messenger.add_subscriber("post_tick", self.client_send_move)

    def can_replicate(self, is_owner, is_initial):
        yield from super().can_replicate(is_owner, is_initial)

        yield "clock"

    @reliable
    def client_correct_move(self, move_id: (int, {'max_value': 1000}), position: Vector, yaw: float, velocity: Vector,
                            angular_yaw: float) -> Netmodes.client:
        """Correct previous move which was mis-predicted.

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
        orientation.z = yaw # TODO is this safe for QUATS
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
            action_states, mouse_delta = state.to_input_state()

            process_inputs(action_states, mouse_delta)
            pawn.tick_physics()

        # Remember this correction, so that older moves are not corrected
        self.latest_correction_id = move_id

    def client_send_move(self):
        """Send inputs, alongside results of applied inputs, to the server."""
        pawn = self.pawn

        # We must have a valid Pawn
        if self.pawn is None:
            return

        position = pawn.transform.world_position
        yaw = pawn.transform.world_orientation.z

        self.server_receive_move(self.move_id, self.latest_correction_id, self.recent_states, position, yaw)

    def get_input_map(self):
        """Return keybinding mapping (from actions to buttons)."""
        file_path = path.join(self.__class__.__name__, "input_map.cfg")
        defaults = {n: str(v) for n, v in InputButtons}
        configuration = self.scene.resource_manager.open_configuration(file_path, defaults=defaults)
        bindings = {n: int(v) for n, v in configuration.items() if isinstance(v, str)}
        return bindings

    def on_destroyed(self):
        if self.scene.world.netmode == Netmodes.server:
            self.scene.messenger.remove_subscriber("tick", self.on_tick)

        else:
            self.scene.world.messenger.remove_subscriber("input_updated", self.client_on_input)
            self.scene.messenger.remove_subscriber("post_tick", self.client_send_move)

    def client_handle_message(self, message: str, player_info: Replicable) -> Netmodes.client:
        """Handle incoming message from another PlayerPawnController.

        :param message: message body
        :param player_info: PlayerReplicationInfo of sending player
        """
        self.scene.messenger.send("message_received", message=message, player_info=player_info)

    def send_message(self, message: str, info: Replicable=None) -> Netmodes.server:
        """Send a message to other PlayerPawnController(s)."""
        self_info = self.info

        # Broadcast to all controllers
        if info is None:
            for replicable in self.scene.replicables.values():
                if not isinstance(replicable, PlayerReplicationInfo):
                    continue

                controller = replicable.owner
                controller.client_handle_message(message, self_info)

        else:
            controller = info.owner
            controller.client_handle_message(message, self_info)

    def set_name(self, name: str)->Netmodes.server:
        self.info.name = name

    def server_on_rtt_estimate_updated(self, rtt):
        """Update ReplicationInfo with approximation of connection ping (RTT/2).

        :param rtt: round trip time from server to client and back
        """
        self.info.ping = rtt / 2

    def server_receive_move(self, move_id: (int, {"max_value": 1000}), latest_correction_id: (int, {'max_value': 1000}),
                            recent_states: (list, {'item_info': TypeInfo(Pointer("input_context.struct_class"))}),
                            position: Vector, yaw: float) -> Netmodes.server:
        """Handle remote client inputs.

        :param move_id: unique ID of move
        :param latest_correction_id: most recent correction ID received by the client
        :param recent_states: list of recent input states
        :param position: position of pawn
        :param yaw: yaw heading of pawn
        """
        push = self.buffer.push

        # Try and push all moves
        try:
            for i, state in enumerate(recent_states):
                push(state, move_id - i)

        except KeyError:
            pass

        # Save physics state for this move for later validation
        self.client_moves_states[move_id] = position, yaw, latest_correction_id

    def process_inputs(self, actions, mouse_delta):
        """Update pawn state using actions and mouse delta

        :param actions: dictionary of action names to button states
        :param mouse_delta: mouse dx, dy values
        """

    def server_validate_last_move(self):
        """Compare server result from client inputs with client's results.

        Send a correction to the client if the move was invalid.
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

        pos_err = (client_position - position).length_squared > self.MAX_POSITION_ERROR_SQUARED
        abs_yaw_diff = ((client_yaw - yaw) % pi) ** 2
        rot_err = min(abs_yaw_diff, pi - abs_yaw_diff) > self.MAX_ORIENTATION_ANGLE_ERROR_SQUARED

        if pos_err or rot_err:
            self.client_correct_move(move_id, position, yaw, velocity, angular_yaw)
            self.last_corrected_move_id = move_id

    def client_on_input(self, input_manager):
        """Handle local inputs from client

        :param input_manager: input manager for world
        """
        action_states = self.input_context.map_to_actions(input_manager.buttons_state, self.input_map)
        mouse_delta = input_manager.mouse_delta
        packed_state = self.input_context.struct_class.from_input_state(action_states, mouse_delta)

        self.move_id += 1
        self.sent_states[self.move_id] = packed_state
        self.recent_states.appendleft(packed_state)

        self.process_inputs(action_states, mouse_delta)

    def server_on_tick(self):
        try:
            input_state, move_id = next(self.buffer)

        except StopIteration:
            return

        except ValueError as err:
            self.logger.error(err)
            return

        if self.pawn is None:
            return

        action_states, mouse_delta = input_state.to_input_state()
        self.process_inputs(action_states, mouse_delta)

        self.pending_validation_move_id = move_id


class Pawn(Actor):
    on_tick_physics = None

    def released_control(self):
        pass

    def controlled_by(self, controller):
        pass

    def tick_physics(self):
        if callable(self.on_tick_physics):
            self.on_tick_physics()