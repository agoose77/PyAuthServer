from network.descriptors import Attribute
from network.decorators import requires_netmode
from network.enums import Netmodes, Roles
from network.replicable import Replicable
from network.signals import LatencyUpdatedSignal
from network.type_flag import Pointer, TypeFlag
from network.world_info import WorldInfo

from .ai.behaviour.behaviour import Node
from .configobj import ConfigObj
from .clock import Clock
from .enums import InputButtons
from .inputs import InputContext
from .latency_compensation import JitterBuffer
from .resources import ResourceManager
from .replication_info import PlayerReplicationInfo
from .signals import PlayerInputSignal


from collections import deque


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

    input_context = InputContext()

    info = Attribute(data_type=Replicable)
    info_cls = PlayerReplicationInfo

    @classmethod
    def get_local_controller(cls):
        """Return the local player controller instance, or None if not found"""
        try:
            return WorldInfo.subclass_of(PlayerPawnController)[0]

        except IndexError:
            return None

    def on_initialised(self):
        """Initialisation method"""
        self.initialise_client()
        self.initialise_server()

        # Network clock
        self.clock = Clock()
        self.clock.possessed_by(self)

    @requires_netmode(Netmodes.client)
    def initialise_client(self):
        """Initialise client-specific player controller state"""
        resources = ResourceManager[self.__class__.__name__]
        file_path = ResourceManager.get_absolute_path(resources['input_map.cfg'])

        parser = ConfigObj(file_path, interpolation="template")
        parser['DEFAULT'] = {k: str(v) for k, v in InputButtons.keys_to_values.items()}

        self.input_map = {name: int(binding) for name, binding in parser.items() if isinstance(binding, str)}
        self.move_id = 0
        self.sent_buffer = deque(maxlen=4)

    @requires_netmode(Netmodes.server)
    def initialise_server(self):
        """Initialise server-specific player controller state"""
        self.info = self.__class__.info_cls()

        self.buffer = JitterBuffer(length=WorldInfo.to_ticks(0.1))

    @LatencyUpdatedSignal.on_context
    def server_update_ping(self, rtt):
        self.info.ping = rtt / 2

    def server_handle_inputs(self, move_id: TypeFlag(int, max_value=WorldInfo.MAXIMUM_TICK),
                             recent_states: TypeFlag(list, element_flag=TypeFlag(
                                 Pointer("input_context.network.struct_cls")))) -> Netmodes.server:
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

    @PlayerInputSignal.on_global
    def handle_inputs(self, delta_time, input_manager):
        """Handle local inputs from client

        :param input_manager: input system
        """
        remapped_state = self.input_context.remap_state(input_manager, self.input_map)
        packed_state = self.input_context.network.struct_cls()
        packed_state.write(remapped_state)

        self.sent_buffer.appendleft(packed_state)
        self.server_handle_inputs(self.move_id, self.sent_buffer)

        self.move_id += 1