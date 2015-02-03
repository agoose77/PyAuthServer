from network.bitfield import BitField
from network.decorators import requires_netmode
from network.descriptors import Attribute, FromClass
from network.enums import Netmodes, Roles
from network.logger import logger
from network.struct import Struct
from network.replicable import Replicable
from network.type_flag import TypeFlag
from network.world_info import WorldInfo


from .ai.behaviour import Node
from .configobj import ConfigObj
from .enums import InputButtons, ButtonState
from .resources import ResourceManager
from .signals import PlayerInputSignal


__all__ = ['PawnController', 'PlayerPawnController', 'AIPawnController']

TICK_FLAG = TypeFlag(int, max_value=WorldInfo._MAXIMUM_TICK)


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


class LocalInputContext:
    """Input context for local inputs"""

    def __init__(self, buttons=None, ranges=None):
        self.buttons = buttons if buttons is not None else []
        self.ranges = ranges if ranges is not None else []

    def remap_state(self, input_manager, keymap):
        """Remap native state to mapped state

        :param input_manager: native state """
        button_state = {}
        range_state = {}

        # Update buttons
        native_button_state = input_manager.buttons
        for mapped_key in self.buttons:
            native_key = keymap.get(mapped_key, mapped_key)
            button_state[mapped_key] = native_button_state[native_key]

        # Update ranges
        native_range_state = input_manager.ranges
        for mapped_key in self.ranges:
            native_key = keymap.get(mapped_key, mapped_key)
            range_state[mapped_key] = native_range_state[native_key]

        return button_state, range_state


class RemoteInputContext:
    """Input context for network inputs"""

    def __init__(self, local_context):
        self.local_context = local_context

        button_count = len(local_context.buttons)
        state_count = len(ButtonState)

        state_bits = button_count * state_count

        class InputStateStruct(Struct):
            """Struct for packing client inputs"""

            _buttons = Attribute(BitField(state_bits), fields=state_bits)
            _ranges = Attribute([], element_flag=TypeFlag(float))

            def write(self, remapped_state):
                button_state = self._buttons
                range_state = self._ranges

                remapped_button_state, remapped_range_state = remapped_state

                # Update buttons
                button_names = local_context.buttons
                for button_index, mapped_key in enumerate(button_names):
                    mapped_state = remapped_button_state[mapped_key]
                    state_index = (button_count * mapped_state) + button_index
                    button_state[state_index] = True

                # Update ranges
                range_state[:] = [remapped_range_state[key] for key in local_context.ranges]

            def read(self):
                button_state = self._buttons[:]
                range_state = self._ranges

                # Update buttons
                button_states = {}
                button_names = local_context.buttons

                for state_index, state in enumerate(button_state):
                    if not state:
                        continue

                    button_index = state_index % button_count
                    mapped_key = button_names[button_index]
                    button_states[mapped_key] = (state_index - button_index) // button_count

                # Update ranges
                range_states = {key: range_state[index] for index, key in enumerate(local_context.ranges)}
                return button_states, range_states

        self.state_struct_cls = InputStateStruct


class PlayerPawnController():
    """Base class for player pawn controllers"""

    input_context = LocalInputContext(buttons=['shoot', 'flinch'])
    remote_input_context = RemoteInputContext(input_context)

    input_cls = remote_input_context.state_struct_cls

    def initialise_client(self):
        """Initialise client-specific player controller state"""
        resources = ResourceManager[self.__class__.__name__]
        file_path = ResourceManager.get_absolute_path(resources['input_map.conf'])

        parser = ConfigObj(file_path)
        parser['DEFAULT'] = {k: str(v) for k, v in InputButtons.keys_to_values.items()}

        self.input_map = {name: int(binding) for name, binding in parser.items()}

    def on_initialised(self):
        if WorldInfo.netmode == Netmodes.client:
            self.initialise_client()

    def server_handle_inputs(self, input_state: TypeFlag(FromClass("input_cls"))):
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