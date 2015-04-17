from game_system.entities import Actor
from game_system.enums import CollisionState
from game_system.signals import LogicUpdateSignal, CollisionSignal


class TestActor(Actor):

    replicate_physics_to_owner = True

    def on_initialised(self):
        super().on_initialised()

        self.transform.world_position = [0, 30, 2]

    @CollisionSignal.on_context
    def on_collided(self, collision_result):
        if collision_result.state == CollisionState.started:
            print([c.impulse for c in collision_result.contacts])

    @LogicUpdateSignal.on_global
    def on_update(self, delta_time):
        # new_pos = self.transform.world_position
        # new_pos.y += 1 / 10
        # self.transform.world_position = new_pos

        velz = self.physics.world_linear_velocity.z
        self.physics.world_linear_velocity = [2, 0, velz]
        pass