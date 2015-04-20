from game_system.entities import Actor
from game_system.enums import CollisionState
from game_system.signals import LogicUpdateSignal, CollisionSignal

from network.descriptors import Attribute
from network.decorators import simulated
from network.enums import Roles


class TestActor(Actor):

    replicate_physics_to_owner = False
    mass = Attribute(0.0, notify=True)
    roles = Attribute(Roles(Roles.authority, Roles.autonomous_proxy))

    def on_initialised(self):
        super().on_initialised()

        self.transform.world_position = [0, 30, 2]

    def conditions(self, is_owner, is_complaint, is_initial):
        yield from super().conditions(is_owner, is_complaint, is_initial)
        yield "mass"

    def on_notify(self, name):
        super().on_notify(name)

        if name == "mass":
            self.physics._game_object.mass = self.mass

    @simulated
    @CollisionSignal.on_context
    def on_collided(self, collision_result):
        pass

    @LogicUpdateSignal.on_global
    def on_update(self, delta_time):
        # new_pos = self.transform.world_position
        # new_pos.y += 1 / 10
        # self.transform.world_position = new_pos
        return