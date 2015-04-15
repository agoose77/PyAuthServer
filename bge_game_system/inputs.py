from game_system.enums import InputButtons, ButtonState

from bge import events, logic
from inspect import getmembers

from game_system.coordinates import Vector
from game_system.inputs import InputState

__all__ = ['BGEInputManager', 'BGEMouseManager']


bge_events = {k: v for k, v in getmembers(events) if k.isupper()}
event_mapping = {e: getattr(InputButtons, v) for v, e in bge_events.items()}
state_mapping = {logic.KX_INPUT_JUST_ACTIVATED: ButtonState.pressed,
                 logic.KX_INPUT_JUST_RELEASED: ButtonState.released,
                 logic.KX_INPUT_ACTIVE: ButtonState.held,
                 logic.KX_INPUT_NONE: ButtonState.none}


class BGEInputManager:
    """Input manager for BGE"""

    def __init__(self):
        self.state = InputState()
        self.mouse_manager = BGEMouseManager()

    def update(self):
        keyboard_events = logic.keyboard.events
        mouse_events = logic.mouse.events

        converted_events = {event_mapping[e]: state_mapping[v]
                            for e, v in keyboard_events.items() if e in event_mapping}
        converted_events.update({event_mapping[e]: state_mapping[v]
                                 for e, v in mouse_events.items() if e in event_mapping})

        self.state.buttons = converted_events

        # Update ranges
        self.mouse_manager.update()

        delta_x, delta_y = self.mouse_manager.delta_position
        self.state.ranges['mouse_delta_x'] = delta_x
        self.state.ranges['mouse_delta_y'] = delta_y

        x, y = self.mouse_manager.position
        self.state.ranges['mouse_x'] = x
        self.state.ranges['mouse_y'] = y


class BGEMouseManager:
    """Interface to mouse information"""

    def __init__(self):
        self.position = Vector((0.0, 0.0))
        self._last_position = Vector((0.0, 0.0))

    @property
    def delta_position(self):
        return self.position - self._last_position

    def update(self):
        """Process new mouse state"""
        position = Vector(logic.mouse.position)

        self._last_position, self.position = self.position, position