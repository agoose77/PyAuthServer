from network.bitfield import BitField
from network.descriptors import Attribute
from network.type_flag import TypeFlag
from network.struct import Struct

from collections import defaultdict

from .enums import ButtonState, InputButtons


__all__ = ['InputState', 'lInputContext', 'NetworkInputContext']


class InputState:
    """Interface to input handlers"""

    def __init__(self):
        self.buttons = {}
        self.ranges = {}


class InputContext:
    """Input context for local inputs"""

    def __init__(self, buttons=None, ranges=None):
        if buttons is None:
            buttons = []

        if ranges is None:
            ranges = []

        self.buttons = buttons
        self.ranges = ranges

        self.network = NetworkInputContext(self.buttons, self.ranges)

    def remap_state(self, input_manager, keymap):
        """Remap native state to mapped state

        :param input_manager: native state
        """
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


class NetworkInputContext:
    """Input context for network inputs"""

    def __init__(self, buttons, ranges):
        button_count = len(buttons)
        state_count = len(ButtonState)

        state_bits = button_count * state_count
        state_indices = {ButtonState.pressed: 0, ButtonState.held: 1, ButtonState.released: 2}

        class InputStateStruct(Struct):
            """Struct for packing client inputs"""

            _buttons = Attribute(BitField(state_bits), fields=state_bits)
            _ranges = Attribute([], element_flag=TypeFlag(float))

            def write(this, remapped_state):
                button_state = this._buttons
                range_state = this._ranges

                remapped_button_state, remapped_range_state = remapped_state

                # Update buttons
                button_names = buttons
                for button_index, mapped_key in enumerate(button_names):
                    mapped_state = remapped_button_state[mapped_key]

                    if mapped_state in state_indices:
                        state_index = state_indices[mapped_state]
                        bitfield_index = (button_count * state_index) + button_index
                        button_state[bitfield_index] = True

                # Update ranges
                range_state[:] = [remapped_range_state[key] for key in ranges]

            def read(this):
                button_state = this._buttons[:]
                range_state = this._ranges

                # Update buttons
                button_names = buttons
                # If the button is omitted, assume not pressed
                button_states = defaultdict(lambda: ButtonState.none)

                for state_index, state in enumerate(button_state):
                    if not state:
                        continue

                    button_index = state_index % button_count
                    mapped_key = button_names[button_index]
                    button_states[mapped_key] = (state_index - button_index) // button_count

                # Update ranges
                range_states = {key: range_state[index] for index, key in enumerate(ranges)}
                return button_states, range_states

        self.struct_cls = InputStateStruct