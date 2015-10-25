from game_system.entity import Actor, MeshComponent, PhysicsComponent, TransformComponent

from network.replication import Serialisable
from network.enums import Roles


class SomeEntity(Actor):

    mesh = MeshComponent("Suzanne")
    physics = PhysicsComponent("Cube", mass=10)
    transform = TransformComponent(position=(0, 10, 0), orientation=(0, 0, 0))

    def __init__(self, scene, unique_id, is_static=False):
        super().__init__(scene, unique_id, is_static)
        scene.messenger.add_subscriber("tick", self.on_update)

    def can_replicate(self, is_owner, is_initial):
        yield from super().can_replicate(is_owner, is_initial)
        yield "score"

    def on_score_replicated(self):
        print(self.score, "Updated")

    def on_update(self):
        #self.transform.world_position += (0, 0.5, 0)
        #print(list())
        self.physics.world_velocity = (0, 0, 9.807*1/60)

    score = Serialisable(data_type=int, notify_on_replicated=True)
    roles = Serialisable(Roles(Roles.authority, Roles.simulated_proxy))