from network.descriptors import Attribute
from network.decorators import requires_netmode, reliable
from network.enums import Netmodes, Roles
from network.logger import logger
from network.replicable import Replicable
from network.rpc import Pointer
from network.signals import LatencyUpdatedSignal
from network.type_flag import TypeFlag
from network.world_info import WorldInfo

from .ai.behaviour.behaviour import Node
from .configobj import ConfigObj
from .clock import Clock
from .coordinates import Vector, Euler
from .enums import InputButtons
from .inputs import InputContext
from .latency_compensation import JitterBuffer
from .resources import ResourceManager
from .replication_info import PlayerReplicationInfo
from .signals import PlayerInputSignal, LogicUpdateSignal, PostPhysicsSignal, PhysicsSingleUpdateSignal


from collections import OrderedDict, deque
from math import radians


__all__ = ['PawnController', 'PlayerPawnController', 'AIPawnController']


class PawnController(Replicable):
    """Base class for Pawn controllers"""

    roles = Attribute(Roles(Roles.authority, Roles.autonomous_proxy))
    pawn = Attribute(data_type=Replicable, complain=True, notify=True)
    info = Attribute(data_type=Replicable, complain=True)

    def conditions(self, is_owner, is_complaint, is_initial):
        yield from super().conditions(is_owner, is_complaint, is_initial)

        if is_complaint:
            yield "pawn"
            yield "info"

    def on_notify(self, name):
        if name == "pawn":
            self.possess(self.pawn)
            print("POSSESS")

    def on_deregistered(self):
        self.pawn.deregister()

        super().on_deregistered()

    def possess(self, pawn):
        """Take control of pawn

        :param pawn: Pawn instance
        """
        self.pawn = pawn
        pawn.possessed_by(self)

    def unpossess(self):
        """Release control of possessed pawn"""
        self.pawn.unpossessed()
        self.pawn = None


class AIPawnController(PawnController):
    """Base class for AI pawn controllers"""

    def on_initialised(self):
        self.blackboard = {}
        self.intelligence = Node()

    def update(self, delta_time):
        blackboard = self.blackboard

        blackboard['delta_time'] = delta_time
        blackboard['pawn'] = self.pawn
        blackboard['controller'] = self

        self.intelligence.evaluate(blackboard)


class PlayerPawnController(PawnController):
    """Base class for player pawn controllers"""

    MAX_POSITION_ERROR_SQUARED = 1
    MAX_ORIENTATION_ANGLE_ERROR_SQUARED = radians(10) ** 2

    input_context = InputContext()

    info = Attribute(data_type=Replicable)
    info_cls = PlayerReplicationInfo

    @classmethod
    def get_local_controller(cls):
        """Return the local player controller instance, or None if not found"""
        try:
            cont = WorldInfo.subclass_of(PlayerPawnController)[0]
            return

        except IndexError:
            return None

    def on_initialised(self):
        """Initialisation method"""
        self.initialise_client()
        self.initialise_server()

    @classmethod
    def get_input_map(cls):
        """Return keybinding mapping (from actions to buttons)"""
        resources = ResourceManager[cls.__name__]
        file_path = ResourceManager.get_absolute_path(resources['input_map.cfg'])

        parser = ConfigObj(file_path, interpolation="template")
        parser['DEFAULT'] = {k: str(v) for k, v in InputButtons.keys_to_values.items()}

        return {name: int(binding) for name, binding in parser.items() if isinstance(binding, str)}

    @requires_netmode(Netmodes.client)
    def initialise_client(self):
        """Initialise client-specific player controller state"""

        self.input_map = self.get_input_map()
        self.move_id = 0

        self.sent_states = OrderedDict()
        self.recent_states = deque(maxlen=5)

    @requires_netmode(Netmodes.server)
    def initialise_server(self):
        """Initialise server-specific player controller state"""
        self.info = self.__class__.info_cls()

        # Network clock
        self.clock = Clock()
        self.clock.possessed_by(self)

        # Network jitter compensation
        self.buffer = JitterBuffer(length=WorldInfo.to_ticks(0.1))

        # Client results of simulating moves
        self.client_moves_states = {}

        # ID of move waiting to be verified
        self.pending_validation_move_id = None
        self.pending_correction_confirmation = False

    @LatencyUpdatedSignal.on_context
    def server_update_ping(self, rtt):
        """Update ReplicationInfo with approximation of connection ping

        :param rtt: round trip time from server to client and back
        """
        self.info.ping = rtt / 2

    def server_receive_move(self, move_id: TypeFlag(int, max_value=WorldInfo.MAXIMUM_TICK),
                            recent_states: TypeFlag(list, element_flag=TypeFlag(
                                 Pointer("input_context.network.struct_cls"))),
                            position: TypeFlag(Vector), orientation: TypeFlag(Euler)) -> Netmodes.server:
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
        self.client_moves_states[move_id] = position, orientation

    # Todo: handle acknowledged moves - pop from sent states
    # Handle older move pop in case no packet received?

    @reliable
    def client_correct_move(self, move_id: TypeFlag(int, max_value=WorldInfo.MAXIMUM_TICK), position: TypeFlag(Vector),
                            orientation: TypeFlag(Euler), velocity: TypeFlag(Vector),
                            angular: TypeFlag(Vector)) -> Netmodes.client:
        """Correct previous move which was mispredicted

        :param move_id: ID of move to correct
        :param position: correct position (of move to correct)
        :param orientation: correct orientation
        :param velocity: correct velocity
        :param angular: correct angular
        """
        pawn = self.pawn
        if not pawn:
            return

        # Restore pawn state
        pawn.transform.world_position = position
        pawn.transform.world_orientation = orientation
        pawn.physics.world_velocity = velocity
        pawn.physics.world_angular = angular

        process_inputs = self.process_inputs
        sent_states = self.sent_states
        delta_time = 1 / WorldInfo.tick_rate

        for move_id in range(move_id, self.move_id + 1):
            state = sent_states[move_id]
            buttons, ranges = state.read()

            process_inputs(buttons, ranges)
            PhysicsSingleUpdateSignal.invoke(delta_time, target=pawn)

        # Inform server of receipt
        self.server_acknowledge_correction()

    def process_inputs(self, buttons, ranges):
        pass

    @reliable
    def server_acknowledge_correction(self) -> Netmodes.server:
        """Acknowledge previous correction sent to client, allowing further corrections"""
        self.pending_correction_confirmation = False

    @requires_netmode(Netmodes.client)
    def client_send_move(self):
        """Send inputs, alongside results of applied inputs, to the server"""
        pawn = self.pawn
        if not pawn:
            return

        position = pawn.transform.world_position
        orientation = pawn.transform.world_orientation

        self.server_receive_move(self.move_id, self.recent_states, position, orientation)

    @requires_netmode(Netmodes.server)
    def server_validate_move(self):
        """Validate result of applied input states.

        Send correction to client if move was invalid.
        """
        pawn = self.pawn
        if not pawn:
            return

        # Don't bother checking if we're already checking invalid state
        if self.pending_correction_confirmation:
            return

        move_id = self.pending_validation_move_id

        try:
            client_state = self.client_moves_states[move_id]

        except KeyError:
            if move_id is not None:
                logger.warn("Unable to verify client state for move: {}".format(move_id))

            return

        client_position, client_orientation = client_state
        position = pawn.transform.world_position

        # Position valid
        if (client_position - position).length_squared <= self.__class__.MAX_POSITION_ERROR_SQUARED:
            return
            # orientation = pawn.transform.world_orientation
            # rotation_difference = orientation.to_quaternion().rotation_difference(client_position).to_euler()

            # # Orientation valid
            # if Vector(orientation_difference).length_squared <= self.__class__.MAX_ORIENTATION_ANGLE_ERROR_SQUARED:
            #     return

        orientation = pawn.transform.world_orientation
        velocity = pawn.physics.world_velocity
        angular = pawn.physics.world_angular

        # Correct client's state
        self.pending_correction_confirmation = True
        self.client_correct_move(move_id, position, orientation, velocity, angular)

    @PlayerInputSignal.on_global
    def client_handle_inputs(self, delta_time, input_manager):
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

    @PostPhysicsSignal.on_global
    def post_physics(self):
        self.client_send_move()
        self.server_validate_move()

    @LogicUpdateSignal.on_global
    @requires_netmode(Netmodes.server)
    def server_update(self, delta_time):
        try:
            state, move_id = next(self.buffer)

        except StopIteration:
            return

        if not self.pawn:
            return

        buttons, ranges = state.read()
        self.process_inputs(buttons, ranges)

        self.pending_validation_move_id = move_id