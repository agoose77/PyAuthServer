from game_system.coordinates import Vector, Quaternion
from game_system.entity import AbstractTransformInstanceComponent, AbstractPhysicsInstanceComponent, InstanceComponent

__all__ = "TransformInstanceComponent", "PhysicsInstanceComponent", "MeshInstanceComponent", \
          "AnimationInstanceComponent", "CameraInstanceComponent"


class BGEInstanceComponent(InstanceComponent):
    pass


class TransformInstanceComponent(AbstractTransformInstanceComponent, BGEInstanceComponent):

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


class PhysicsInstanceComponent(AbstractPhysicsInstanceComponent, BGEInstanceComponent):

    def __init__(self, entity, game_object, component):
        self._entity = entity
        self._game_object = game_object

        self._class_component = component

    @property
    def mass(self):
        return self._game_object.mass

    @mass.setter
    def mass(self, value):
        self._game_object.mass = value

    @property
    def world_velocity(self):
        try:
            return self._game_object.worldLinearVelocity.copy()

        except AttributeError:
            return Vector()

    @world_velocity.setter
    def world_velocity(self, value):
        self._game_object.worldLinearVelocity = value

    @property
    def world_angular(self):
        try:
            return self._game_object.worldAngularVelocity.copy()

        except AttributeError:
            return Vector()

    @world_angular.setter
    def world_angular(self, value):
        self._game_object.worldAngularVelocity = value

    def apply_force(self, force, position=None):
        if position is not None:
            raise RuntimeError("BGE doesn't support position")

        self._game_object.applyForce(force)

    def apply_impulse(self, impulse, position):
        self._game_object.applyImpulse(position, impulse)

    def apply_torque(self, torque):
        self._game_object.applyTorque(torque)

    def on_destroyed(self):
        pass


class MeshInstanceComponent(BGEInstanceComponent):

    def __init__(self, entity, game_object, component):
        pass


class AnimationInstanceComponent(BGEInstanceComponent):

    def __init__(self, entity, game_object, component):
        pass


class CameraInstanceComponent(BGEInstanceComponent):

    def __init__(self, entity, game_object, component):
        pass