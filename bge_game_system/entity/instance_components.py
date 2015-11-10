from game_system.coordinates import Vector
from game_system.entity import AbstractTransformInstanceComponent, AbstractPhysicsInstanceComponent

__all__ = "TransformInstanceComponent", "PhysicsInstanceComponent", "MeshInstanceComponent", \
          "AnimationInstanceComponent", "CameraInstanceComponent"


class TransformInstanceComponent(AbstractTransformInstanceComponent):

    def __init__(self, entity, game_object, component):
        self._game_object = game_object

        if component.position:
            self.world_position = component.position

        if component.orientation:
            self.world_orientation = component.orientation

    def move(self, dr, local=False):
        if not local:
            self._game_object.worldPosition += Vector(dr)

        else:
            self._game_object.localPosition += Vector(dr)

    @property
    def world_position(self):
        return self._game_object.worldPosition

    @world_position.setter
    def world_position(self, position):
        self._game_object.worldPosition = position

    @property
    def world_orientation(self):
        return self._game_object.worldOrientation.to_euler()

    @world_orientation.setter
    def world_orientation(self, orientation):
        self._game_object.worldOrientation = orientation


class PhysicsInstanceComponent(AbstractPhysicsInstanceComponent):

    def __init__(self, entity, game_object, component):
        pass


class MeshInstanceComponent:

    def __init__(self, entity, game_object, component):
        pass


class AnimationInstanceComponent:

    def __init__(self, entity, game_object, component):
        pass


class CameraInstanceComponent:

    def __init__(self, entity, game_object, component):
        pass