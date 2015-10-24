from game_system.entity import Entity, Actor
from game_system.scene import Scene as _Scene

from .entity import EntityBuilder
from .physics import PhysicsManager

from bge import logic


class Scene(_Scene):

    def __init__(self, world, name, input_manager):
        super().__init__(world, name)

        self._bge_scene = next(s for s in logic.getSceneList() if s.name == name)
        self._entity_builder = EntityBuilder(self._bge_scene, input_manager)

        self.physics_manager = PhysicsManager()

        self.messenger.add_subscriber("replicable_created", self.on_replicable_created)

    @property
    def active_camera(self):
        return self.active_camera

    @active_camera.setter
    def active_camera(self, camera):
        self.active_camera = camera

    def on_replicable_created(self, replicable):
        if isinstance(replicable, Entity):
            self._entity_builder.load_entity(replicable)

            if isinstance(replicable, Actor):
                pass
