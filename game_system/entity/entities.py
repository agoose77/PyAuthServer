from network.replicable import Replicable
from network.replication import Struct, Serialisable

from .builder import EntityMetacls
from .class_components import TransformComponent, PhysicsComponent
from ..coordinates import Vector, Quaternion


class Entity(Replicable, metaclass=EntityMetacls):
    """Base class for networked component holders"""


class PhysicsState(Struct):
    mass = Serialisable(data_type=float)
    position = Serialisable(data_type=Vector)
    orientation = Serialisable(data_type=Quaternion)
    tick = Serialisable(data_type=int, max_value=1000000)
    # TODO dont send vel / angular
    # TODO use quaternions instead of euler - compress them


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

            if callable(self.on_physics_replicated):
                self.on_physics_replicated()

        else:
            super().on_replicated(name)
