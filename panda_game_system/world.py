from game_system.world import World as _World

from .input import InputManager
from .scene import Scene


class World(_World):

    scene_class = Scene

    def _create_input_manager(self):
        return InputManager(self)
