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

        self.physics_manager = PhysicsManager(self._root_nodepath, world)

    def _create_entity_builder(self):
        return EntityBuilder(self._root_nodepath)

    def _on_tick(self):
        self.physics_manager.tick()

        super()._on_tick()
