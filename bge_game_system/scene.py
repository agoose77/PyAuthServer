from game_system.entity import Entity, Actor
from game_system.scene import Scene as _Scene

from .entity import EntityBuilder
from .physics import PhysicsManager

from bge import logic


class Scene(_Scene):

    def __init__(self, world, name):
        super().__init__(world, name)

        try:
            scene = next(s for s in logic.getSceneList() if s.name == name)

        except StopIteration:
            scene = logic.addScene(name)

        self.bge_scene = scene
        self.entity_builder = EntityBuilder(self.bge_scene)
        self.physics_manager = PhysicsManager()

    @property
    def active_camera(self):
        return self.active_camera

    @active_camera.setter
    def active_camera(self, camera):
        self.active_camera = camera

    def _on_replicable_created(self, replicable):
        if isinstance(replicable, Entity):
            self.entity_builder.load_entity(replicable)

            if isinstance(replicable, Actor):
                pass

        super()._on_replicable_created(replicable)