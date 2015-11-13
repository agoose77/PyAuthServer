from game_system.coordinates import Vector, Quaternion
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
        return self._game_object.worldOrientation.to_quaternion()

    @world_orientation.setter
    def world_orientation(self, orientation):
        assert isinstance(orientation, Quaternion)
        self._game_object.worldOrientation = orientation


class PhysicsInstanceComponent(AbstractPhysicsInstanceComponent):

    def __init__(self, entity, game_object, component):
        self._game_object = game_object

    @property
    def mass(self):
        return self._game_object.mass

    @mass.setter
    def mass(self, mass):
        self._game_object.mass = mass

    @property
    def world_velocity(self):
        return self._game_object.worldLinearVelocity

    @world_velocity.setter
    def world_velocity(self, velocity):
        self._game_object.worldLinearVelocity = velocity

    @property
    def world_angular(self):
        return self._game_object.worldAngularVelocity

    @world_angular.setter
    def world_angular(self, angular):
        self._game_object.worldAngularVelocity = angular


class MeshInstanceComponent:

    def __init__(self, entity, game_object, component):
        pass


class AnimationInstanceComponent:

    def __init__(self, entity, game_object, component):
        pass


class CameraInstanceComponent:

    def __init__(self, entity, game_object, component):
        pass