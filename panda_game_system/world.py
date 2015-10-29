from game_system.world import World as _World

from .scene import Scene


class World(_World):

    scene_class = Scene