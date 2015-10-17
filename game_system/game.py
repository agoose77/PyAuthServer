class Game:

    def __init__(self, world, network_manager):
        self.world = world
        self.network_manager = network_manager

        world.messenger.add_subscriber("scene_added", self.configure_scene)

    def configure_scene(self, scene):
        raise NotImplementedError()