from network.enums import Netmodes
from functools import partial


class NetworkPhysicsManager:

    def __init__(self, world):
        self._entities = set()
        self._time = 0.0

        self._world = world
        self._timestep = 1 / world.tick_rate

    def add_actor(self, actor):
        self._entities.add(actor)
        actor.on_physics_replicated = partial(self.on_replicated, actor)

    def remove_actor(self, actor):
        self._entities.remove(actor)
        actor.on_physics_replicated = None

    def write_to_network(self):
        timestamp = self._time

        for entity in self._entities:
            physics_state = entity.physics_state
            physics_state.position = entity.transform.world_position
            physics_state.orientation = entity.transform.world_orientation
            physics_state.velocity = entity.physics.world_velocity
            physics_state.angular = entity.physics.world_angular
            physics_state.timestamp = timestamp

    def on_replicated(self, entity):
        physics_state = entity.physics_state
        entity.transform.world_position = physics_state.position
        entity.transform.world_orientation = physics_state.orientation
        entity.physics.world_velocity = physics_state.velocity
        entity.physics.world_angular = physics_state.angular

    def tick(self):
        if self._world.netmode == Netmodes.server:
            self.write_to_network()

        self._time += self._timestep