from network.descriptors import Attribute, FromClass
from network.enums import Netmodes, Roles
from network.replicable import Replicable
from network.type_flag import TypeFlag
from network.world_info import WorldInfo


from .ai.behaviour.behaviour import Node
from .configobj import ConfigObj
from .enums import InputButtons
from .inputs import LocalInputContext, RemoteInputContext
from .resources import ResourceManager
from .signals import PlayerInputSignal


__all__ = ['PawnController', 'PlayerPawnController', 'AIPawnController']


class PawnController(Replicable):
    """Base class for Pawn controllers"""

    roles = Attribute(Roles(Roles.authority, Roles.autonomous_proxy))
    pawn = Attribute(type_of=Replicable, complain=True, notify=True)
    info = Attribute(type_of=Replicable, complain=True)

    def conditions(self, is_owner, is_complaint, is_initial):
        yield from super().conditions(is_owner, is_complaint, is_initial)

        if is_complaint:
            yield "pawn"
            yield "info"

    def on_notify(self, name):
        if name == "pawn":
            self.possess(self.pawn)

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

    input_context = LocalInputContext(buttons=['shoot', 'flinch'])
    remote_input_context = RemoteInputContext(input_context)

    def on_initialised(self):
        if WorldInfo.netmode == Netmodes.client:
            self.initialise_client()

    @classmethod
    def get_local_controller(cls):
        """Return the local player controller instance, or None if not found"""
        try:
            return WorldInfo.subclass_of(PlayerPawnController)[0]
        except IndexError:
            return None

    def initialise_client(self):
        """Initialise client-specific player controller state"""
        resources = ResourceManager[self.__class__.__name__]
        file_path = ResourceManager.get_absolute_path(resources['input_map.conf'])

        parser = ConfigObj(file_path, interpolation="template")
        parser['DEFAULT'] = {k: str(v) for k, v in InputButtons.keys_to_values.items()}
        self.input_map = {name: int(binding) for name, binding in parser.items() if isinstance(binding, str)}

    def server_handle_inputs(self, input_state: TypeFlag(FromClass("remote_input_context.state_struct_cls"))):
        """Handle remote client inputs

        :param input_state: state of inputs
        """
        mapped_state = input_state.read()

    @PlayerInputSignal.on_global
    def handle_inputs(self, delta_time, input_manager):
        """Handle local inputs from client

        :param input_manager: input system
        """
        remapped_state = self.input_context.remap_state(input_manager, self.input_map)

        packed_state = self.remote_input_context.state_struct_cls()
        packed_state.write(remapped_state)

        return packed_state