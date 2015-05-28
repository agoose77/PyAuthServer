from network.descriptors import Attribute
from network.decorators import requires_netmode, reliable
from network.enums import Netmodes, Roles
from network.logger import logger
from network.replicable import Replicable
from network.rpc import Pointer
from network.signals import Signal, LatencyUpdatedSignal
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
from .signals import PlayerInputSignal, LogicUpdateSignal, PostPhysicsSignal, PhysicsSingleUpdateSignal, \
    MessageReceivedSignal


from collections import OrderedDict, deque
from math import radians, pi


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

    def on_deregistered(self):
        self.pawn.deregister()

        super().on_deregistered()

    def possess(self, pawn):
        """Take control of pawn

        :param pawn: Pawn instance
        """
        self.pawn = pawn
        pawn.possessed_by(self)

        # Set pawn as parent for signals
        pawn.register_child(self, greedy=True)

    def unpossess(self):
        """Release control of possessed pawn"""
        pawn = self.pawn

        # Set pawn as parent for signals
        pawn.unregister_child(self, greedy=True)
        pawn.unpossessed()

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

    MAX_POSITION_ERROR_SQUARED = 0.5
    MAX_ORIENTATION_ANGLE_ERROR_SQUARED = radians(5) ** 2

    input_context = InputContext()

    clock = Attribute(data_type=Replicable, complain=True)

    info_cls = PlayerReplicationInfo

    @classmethod
    def get_local_controller(cls):
        """Return the local player controller instance, or None if not found"""
        return next(iter(Replicable.subclass_of_type(PlayerPawnController)), None)

    def on_initialised(self):
        """Initialisation method"""
        self.initialise_client()
        self.initialise_server()

    def conditions(self, is_owner, is_complaint, is_initial):
        yield from super().conditions(is_owner, is_complaint, is_initial)

        if is_complaint:
            yield "clock"

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
        self.latest_correction_id = 0

        self.sent_states = OrderedDict()
        self.recent_states = deque(maxlen=5)

    @requires_netmode(Netmodes.server)
    def initialise_server(self):
        """Initialise server-specific player controller state"""
        self.info = self.__class__.info_cls()
        self.info.possessed_by(self)

        # Network clock
        self.clock = Clock()
        self.clock.possessed_by(self)

        # Network jitter compensation
        self.buffer = JitterBuffer(length=WorldInfo.to_ticks(0.1))

        # Client results of simulating moves
        self.client_moves_states = {}

        # ID of move waiting to be verified
        self.pending_validation_move_id = None
        self.last_corrected_move_id = 0

    def receive_message(self, message: TypeFlag(str), info: TypeFlag(Replicable)) -> Netmodes.client:
        MessageReceivedSignal.invoke(message, info)

    def send_message(self, message: TypeFlag(str), info: TypeFlag(Replicable)=None) -> Netmodes.server:
        self_info = self.info

        # Broadcast to all controllers
        if info is None:
            for info in Replicable.subclass_of_type(PlayerReplicationInfo).copy():
                controller = info.owner
                controller.receive_message(message, self_info)

        else:
            controller = info.owner
            controller.receive_message(message, self_info)

    def set_name(self, name: TypeFlag(str))->Netmodes.server:
        self.info.name = name

    @LatencyUpdatedSignal.on_context
    def server_update_ping(self, rtt):
        """Update ReplicationInfo with approximation of connection ping

        :param rtt: round trip time from server to client and back
        """
        self.info.ping = rtt / 2

    def server_receive_move(self, move_id: TypeFlag(int, max_value=WorldInfo.MAXIMUM_TICK),
                            latest_correction_id: TypeFlag(int, max_value=WorldInfo.MAXIMUM_TICK),
                            recent_states: TypeFlag(list, element_flag=TypeFlag(
                                Pointer("input_context.network.struct_cls"))),
                            position: TypeFlag(Vector), yaw: TypeFlag(float)) -> Netmodes.server:
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

    @reliable
    def client_correct_move(self, move_id: TypeFlag(int, max_value=WorldInfo.MAXIMUM_TICK), position: TypeFlag(Vector),
                            yaw: TypeFlag(float), velocity: TypeFlag(Vector),
                            angular_yaw: TypeFlag(float)) -> Netmodes.client:
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
        delta_time = 1 / WorldInfo.tick_rate

        # Correcting move
        print("Correcting an invalid move: {}".format(move_id))

        for move_id in range(move_id, self.move_id + 1):
            state = sent_states[move_id]
            buttons, ranges = state.read()

            process_inputs(buttons, ranges)
            PhysicsSingleUpdateSignal.invoke(delta_time, target=pawn)

        # Remember this correction, so that older moves are not corrected
        self.latest_correction_id = move_id

    def process_inputs(self, buttons, ranges):
        pass

    @requires_netmode(Netmodes.client)
    def client_send_move(self):
        """Send inputs, alongside results of applied inputs, to the server"""
        pawn = self.pawn
        if not pawn:
            return

        position = pawn.transform.world_position
        yaw = pawn.transform.world_orientation.z

        self.server_receive_move(self.move_id, self.latest_correction_id, self.recent_states, position, yaw)

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
        self.server_validate_last_move()

    @LogicUpdateSignal.on_global
    @requires_netmode(Netmodes.server)
    def server_update(self, delta_time):
        try:
            input_state, move_id = next(self.buffer)

        except StopIteration:
            return

        if not self.pawn:
            return

        buttons, ranges = input_state.read()
        self.process_inputs(buttons, ranges)

        self.pending_validation_move_id = move_id