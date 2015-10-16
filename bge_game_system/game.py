from game_system.game import Game as _Game

from .entity import EntityBuilder


class Game(_Game):

    def __init__(self, world, network_manager):
        super().__init__(world, network_manager)

        self.entity_configurators = {}

    def configure_scene(self, scene):
        self.entity_configurators[scene] = configurator = EntityBuilder()

        scene.messenger.add_subscriber("replicable_created", configurator.load_entity)
        scene.messenger.add_subscriber("replicable_destroyed", configurator.unload_entity)
