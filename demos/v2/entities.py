from game_system.entity import Actor, MeshComponent, PhysicsComponent, TransformComponent

from network.replication import Serialisable
from network.enums import Roles


class SomeEntity(Actor):
    mesh = MeshComponent("Suzanne")
    physics = PhysicsComponent("Cube", mass=100)
    transform = TransformComponent(position=(0, 10, 0), orientation=(0, 0, 0))

    def __init__(self, scene, unique_id, is_static=False):
        super().__init__(scene, unique_id, is_static)

        scene.messenger.add_subscriber("tick", self.on_update)
        self.messenger.add_subscriber("collision_started", self.on_collide)

    def on_destroyed(self):
        self.scene.messenger.remove_subscriber("tick", self.on_update)
        self.messenger.remove_subscriber("collision_started", self.on_collide)

        super().on_destroyed()

    def can_replicate(self, is_owner, is_initial):
        yield from super().can_replicate(is_owner, is_initial)

        yield "score"

    def on_score_replicated(self):
        print(self.score, "Updated")

    def on_collide(self, entity, contacts):
        print("COLLIDED", list(contacts))

    def on_update(self):
        pass

    score = Serialisable(data_type=int, notify_on_replicated=True)
    roles = Serialisable(Roles(Roles.authority, Roles.simulated_proxy))