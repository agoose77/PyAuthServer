from game_system.entities import Actor
from game_system.enums import CollisionState
from game_system.signals import LogicUpdateSignal, CollisionSignal

from network.descriptors import Attribute
from network.decorators import simulated
from network.enums import Roles


class TestActor(Actor):
    mass = Attribute(1.0, notify=True)
    roles = Attribute(Roles(Roles.authority, Roles.autonomous_proxy))

    replicate_physics_to_owner = False

    def on_initialised(self):
        super().on_initialised()

        self.transform.world_position = [0, 30, 2]

    def conditions(self, is_owner, is_complaint, is_initial):
        yield from super().conditions(is_owner, is_complaint, is_initial)

        yield "mass"

    def on_notify(self, name):
        if name == "mass":
            self.physics.mass = self.mass
        else:
            super().on_notify(name)

    @simulated
    @CollisionSignal.on_context
    def on_collided(self, collision_result):
        pass

    @LogicUpdateSignal.on_global
    def on_update(self, delta_time):

        # new_pos = self.transform.world_position
        # new_pos.z -= 1 / 200
        # self.transform.world_position = new_pos
        return