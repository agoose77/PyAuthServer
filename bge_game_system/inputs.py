from game_system.enums import InputButtons, ButtonState

from bge import events, logic
from inspect import getmembers

from game_system.coordinates import Vector
from game_system.inputs import InputState

__all__ = ['BGEInputManager', 'BGEMouseManager']


bge_events = {k: v for k, v in getmembers(events) if k.isupper()}


class BGEInputManager:
    """Input manager for BGE"""

    def __init__(self):
        self.state = InputState()

        self.event_mapping = {e: getattr(InputButtons, v) for v, e in bge_events.items()}
        self.state_mapping = {logic.KX_INPUT_JUST_ACTIVATED: ButtonState.pressed,
                              logic.KX_INPUT_JUST_RELEASED: ButtonState.released,
                              logic.KX_INPUT_ACTIVE: ButtonState.held,
                              logic.KX_INPUT_NONE: ButtonState.none}

        self.mouse_manager = BGEMouseManager()

    def update(self):
        state_mapping = self.state_mapping
        event_mapping = self.event_mapping

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
        self._last_position = Vector()
        self.visible = False

    @property
    def delta_position(self):
        return self.position - self._last_position

    def update(self):
        """Process new mouse state

        :param position: new mouse position
        :param visible: new mouse visibility state
        """
        position = Vector(logic.mouse.position)
        visible = logic.mouse.visible

        self._last_position, self.position = self.position, position
        self.visible = visible