from game_system.enums import InputButtons, ButtonState

from bge import events, logic

from game_system.coordinates import Vector
from game_system.inputs import InputState

__all__ = ['BGEInputManager', 'BGEMouseManager']


bge_events = {getattr(events, k): k for k in dir(events) if k.isupper()}


class BGEInputManager:
    """Input manager for BGE"""

    def __init__(self):
        self.state = InputState()

        self.event_mapping = {bge_events[e]: getattr(InputButtons, e) for e in bge_events.values()}
        self.state_mapping = {logic.KX_INPUT_JUST_ACTIVATED: ButtonState.pressed,
                              logic.KX_INPUT_JUST_RELEASED: ButtonState.released,
                              logic.KX_INPUT_ACTIVE: ButtonState.held}

        self.mouse_manager = BGEMouseManager()

    def update(self):
        event_mapping = self.event_mapping
        state_mapping = self.state_mapping

        self.state.buttons = {event_mapping[k]: state_mapping[v] for k, v in logic.keyboard.active_events.items()}

        # Update ranges
        self.mouse_manager.update()

        delta_x, delta_y = self.mouse_manager.delta_position
        self.state.ranges['mouse_delta_x'] = delta_x
        self.state.ranges['mouse_delta_y'] = delta_y

        x, y = self.mouse_manager.delta_position
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
        position = logic.mouse.position
        visible = logic.mouse.visible

        self._last_position, self.position = self.position, position
        self.visible = visible