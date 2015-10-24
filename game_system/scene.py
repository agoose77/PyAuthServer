from network.scene import Scene as _Scene

from .resources import ResourceManager
from .physics import NetworkPhysicsManager


class Scene(_Scene):

    def __init__(self, world, name):
        super().__init__(world, name)

        self.resource_manager = ResourceManager(world.root_filepath)
        self.network_physics_manager = NetworkPhysicsManager()