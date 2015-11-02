from game_system.entity import Actor, MeshComponent, PhysicsComponent, TransformComponent

from network.annotations.decorators import simulated
from network.replication import Serialisable
from network.enums import Roles


class SomeEntity(Actor):
    mesh = MeshComponent("Suzanne")
    physics = PhysicsComponent("Cube", mass=200)
    transform = TransformComponent(position=(0, 10, 0))

    roles = Serialisable(Roles(Roles.authority, Roles.simulated_proxy))

    def __init__(self, scene, unique_id, is_static=False):
        scene.messenger.add_subscriber("tick", self.on_update)
        self.messenger.add_subscriber("collision_started", self.on_collide)

    def on_destroyed(self):
        self.scene.messenger.remove_subscriber("tick", self.on_update)
        self.messenger.remove_subscriber("collision_started", self.on_collide)

        super().on_destroyed()

    def can_replicate(self, is_owner, is_initial):
        yield from super().can_replicate(is_owner, is_initial)

    def on_collide(self, entity, contacts):
        if not self.physics.mass:
            return

        self.physics.apply_impulse((0, 0, 500), (0, 0, 0))

    @simulated
    def on_update(self):
        pass