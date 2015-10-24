from game_system.entity import Entity, MeshComponent, TransformComponent, InputComponent

from network.replication import Serialisable
from network.enums import Roles


class SomeEntity(Entity):

    mesh = MeshComponent("Suzanne")
    transform = TransformComponent(position=(0, 0, 0), orientation=(0, 0, 0))

    def can_replicate(self, is_owner, is_initial):
        yield from super().can_replicate(is_owner, is_initial)
        yield "score"

    def on_replicated(self, name):
        print(name, "replicated!")

    def on_score_replicated(self):
        print(self.score, "Updated")

    score = Serialisable(data_type=int, notify_on_replicated=True)
    roles = Serialisable(Roles(Roles.authority, Roles.simulated_proxy))