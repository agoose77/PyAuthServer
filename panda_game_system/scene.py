from game_system.entity import Entity, Actor
from game_system.scene import Scene as _Scene

from .entity import EntityBuilder
from .physics import PhysicsManager

from panda3d.core import NodePath


class Scene(_Scene):

    def __init__(self, world, name):
        super().__init__(world, name)

        # Root nodepath
        self._root_nodepath = NodePath(name)
        self._root_nodepath.reparent_to(base.render)

        self.entity_builder = EntityBuilder(self._root_nodepath)
        self.physics_manager = PhysicsManager(self._root_nodepath, world)

    def _on_replicable_created(self, replicable):
        if isinstance(replicable, Entity):
            self.entity_builder.load_entity(replicable)

        super()._on_replicable_created(replicable)

    def _on_replicable_destroyed(self, replicable):
        if isinstance(replicable, Entity):
            self.entity_builder.unload_entity(replicable)

        super()._on_replicable_destroyed(replicable)

    def _on_tick(self):
        self.physics_manager.tick()

        super()._on_tick()
