from network.replicable import Replicable
from network.struct import Struct
from network.replication import Serialisable

from .builder import EntityMetacls
from .class_components import TransformComponent, PhysicsComponent
from ..coordinates import Vector, Euler


class Entity(Replicable, metaclass=EntityMetacls):
    """Base class for networked component holders"""


class PhysicsState(Struct):
    position = Serialisable(data_type=Vector)
    velocity = Serialisable(data_type=Vector)
    orientation = Serialisable(data_type=Euler)
    angular = Serialisable(data_type=Vector)
    timestamp = Serialisable(data_type=float)


class Actor(Entity):
    transform = TransformComponent()
    physics = PhysicsComponent()

    physics_state = Serialisable(PhysicsState(), notify_on_replicated=True)

    on_physics_replicated = None

    def can_replicate(self, is_owner, is_initial):
        yield from super().can_replicate(is_owner, is_initial)

        yield "physics_state"

    def on_replicated(self, name):
        if name == "physics_state":
            print(self, self.on_physics_replicated)
            if callable(self.on_physics_replicated):
                self.on_physics_replicated()

        else:
            super().on_replicated(name)
