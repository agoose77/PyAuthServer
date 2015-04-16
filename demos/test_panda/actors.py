from game_system.entities import Actor
from game_system.signals import LogicUpdateSignal, CollisionSignal


class TestActor(Actor):

    replicate_physics_to_owner = True

    def on_initialised(self):
        super().on_initialised()

        self.transform.world_position = [0, 30, 2]

    @CollisionSignal.on_context
    def on_collided(self, collision_result):
        print(collision_result)

    @LogicUpdateSignal.on_global
    def on_update(self, delta_time):
        # new_pos = self.transform.world_position
        # new_pos.y += 1 / 10
        # self.transform.world_position = new_pos

        #self.physics.world_linear_velocity = [5, 10, 0]
        pass