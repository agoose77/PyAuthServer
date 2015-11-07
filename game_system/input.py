from .enums import ButtonStates

from network.bitfield import BitField
from network.replication import Struct, Serialisable


class InputContext:
    """Input context for local inputs"""

    def __init__(self, *action_names):
        if len(action_names) != len(set(action_names)):
            raise ValueError("Action names provided contain duplicates: {}".format(action_names))

        self.button_names = action_names
        self.struct_class = create_input_struct(action_names)

    def map_to_actions(self, buttons, keymap):
        """Remap native state to mapped state"""
        remapped_buttons = {}

        for action_name in self.button_names:
            button_name = keymap.get(action_name, action_name)
            remapped_buttons[action_name] = buttons[button_name]

        return remapped_buttons


def create_input_struct(action_names):
    action_count = len(action_names)

    class InputStateStruct(Struct):
        """Struct for packing client inputs"""

        state_a = Serialisable(BitField(action_count), fields=action_count)
        state_b = Serialisable(BitField(action_count), fields=action_count)

        mouse_delta_x = Serialisable(data_type=float)
        mouse_delta_y = Serialisable(data_type=float)

        @classmethod
        def from_input_state(cls, actions_state, mouse_delta):
            self = cls()

            state_a = self.state_a
            state_b = self.state_b

            # Update buttons
            for index, action_name in enumerate(action_names):
                state = actions_state[action_name]

                if state == ButtonStates.pressed:
                    state_a[index] = True

                elif state == ButtonStates.released:
                    state_b[index] = True

                elif state == ButtonStates.held:
                    state_a[index] = state_b[index] = True

            self.mouse_delta_x, self.mouse_delta_y = mouse_delta
            return self

        def to_input_state(self):
            state_a = self.state_a
            state_b = self.state_b

            actions_state = {}

            # Update buttons
            for index, action_name in enumerate(action_names):
                a = state_a[index]
                b = state_b[index]

                if a and b:
                    actions_state[action_name] = ButtonStates.held

                elif a:
                    actions_state[action_name] = ButtonStates.pressed

                elif b:
                    actions_state[action_name] = ButtonStates.released

                else:
                    actions_state[action_name] = ButtonStates.none

            mouse_delta = self.mouse_delta_x, self.mouse_delta_y

            return actions_state, mouse_delta

    return InputStateStruct


class InputManagerBase:

    def __init__(self, world):
        self._world = world

        # Configuration
        self.confine_mouse = False
        self.constrain_center_mouse = False
        self.mouse_visible = False

        self.mouse_position = None
        self.mouse_delta = None
        self.buttons_state = {}

    def tick(self):
        raise NotImplementedError
