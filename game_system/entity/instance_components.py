__all__ = "InstanceComponent", "AbstractPhysicsInstanceComponent", "AbstractTransformInstanceComponent", \
          "AbstractMeshInstanceComponent"


class InstanceComponent:

    def on_destroyed(self):
        pass


class NotImplementedProperty:

    def __get__(self, instance, cls):
        if instance is None:
            return self

        raise NotImplementedError

    def __set__(self, instance, value):
        raise NotImplementedError


class AbstractTransformInstanceComponent(InstanceComponent):
    """Abstract base class for physics instance component"""

    world_position = NotImplementedProperty()
    world_orientation = NotImplementedProperty()
    local_position = NotImplementedProperty()
    local_orientation = NotImplementedProperty()


class AbstractPhysicsInstanceComponent(InstanceComponent):
    """Abstract base class for physics instance component"""

    world_velocity = NotImplementedProperty()
    world_angular = NotImplementedProperty()
    local_velocity = NotImplementedProperty()
    local_angular = NotImplementedProperty()

    def integrate_tick(self):
        raise NotImplemented


class AbstractMeshInstanceComponent(InstanceComponent):
    pass
