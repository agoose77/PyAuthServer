from network.scene import Scene as _Scene

from .entity import Actor, Entity
from .resources import ResourceManager
from .timers import TimerManager
from .physics import create_network_physics_manager


from os import path


class Scene(_Scene):

    def __init__(self, world, name):
        super().__init__(world, name)

        self.timer_manager = TimerManager()
        self.resource_manager = ResourceManager(path.join(world.root_filepath, name))
        self.network_physics_manager = create_network_physics_manager(world)
        self.entity_builder = self._create_entity_builder()

        self.messenger.add_subscriber("replicable_created", self._on_replicable_created)
        self.messenger.add_subscriber("replicable_removed", self._on_replicable_destroyed)

    def _create_entity_builder(self):
        raise NotImplementedError

    def _on_replicable_created(self, replicable):
        if isinstance(replicable, Entity):
            self.entity_builder.load_entity(replicable)

        if isinstance(replicable, Actor):
            self.network_physics_manager.add_actor(replicable)

    def _on_replicable_destroyed(self, replicable):
        if isinstance(replicable, Actor):
            self.network_physics_manager.remove_actor(replicable)

        if isinstance(replicable, Entity):
            self.entity_builder.unload_entity(replicable)

    def _on_tick(self):
        self.network_physics_manager.tick()
        self.timer_manager.update(1 / self.world.tick_rate)

    def tick(self):
        self.messenger.send("tick")
        self._on_tick()
        self.messenger.send("post_tick")
