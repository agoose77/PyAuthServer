from game_system.input import InputManagerBase

from bge import logic


class InputManager(InputManagerBase):

    @property
    def mouse_position(self):
        x, y = logic.mouse.position
        return x, y

    @property
    def current_events(self):
        return {}