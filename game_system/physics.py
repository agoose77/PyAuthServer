from network.enums import Netmodes, Roles
from functools import partial

from .latency_compensation import InterpolationWindow


class INetworkPhysicsManager:

    def __init__(self, world):
        pass

    def add_actor(self, actor):
        raise NotImplementedError

    def remove_actor(self, actor):
        raise NotImplementedError

    def tick(self):
        raise NotImplementedError


class ServerNetworkPhysicsManager(INetworkPhysicsManager):

    def __init__(self, world):
        self._timestep = 1 / world.tick_rate
        self._world = world

        self._entities = set()

    def add_actor(self, actor):
        self._entities.add(actor)

    def remove_actor(self, actor):
        self._entities.remove(actor)

    def tick(self):
        current_tick = self._world.current_tick

        for entity in self._entities:
            physics_state = entity.physics_state
            physics_state.position = entity.transform.world_position
            physics_state.orientation = entity.transform.world_orientation
            physics_state.velocity = entity.physics.world_velocity
            physics_state.angular = entity.physics.world_angular
            physics_state.tick = current_tick
            physics_state.mass = entity.physics.mass


class ClientNetworkPhysicsManager(INetworkPhysicsManager):

    def __init__(self, world):
        self._entity_to_interpolator = {}

        self._time = 0.0
        self._timestep = 1 / world.tick_rate
        self._world = world
        self._latency = 0.0

        # Listen for latency message
        world.messenger.add_subscriber("server_latency_estimate", self._update_latency_estimate)

    def add_actor(self, actor):
        interpolator = InterpolationWindow()
        self._entity_to_interpolator[actor] = interpolator
        actor.on_physics_replicated = partial(self.on_replicated, actor, interpolator)

    def remove_actor(self, actor):
        del self._entity_to_interpolator[actor]
        actor.on_physics_replicated = None

    def on_replicated(self, actor, interpolator):
        physics_state = actor.physics_state

        interpolator.add_frame(physics_state.tick, physics_state.position, physics_state.orientation)

        # Non time varying
        actor.physics.mass = physics_state.mass
        #actor.physics.collision_group
        #actor.physics.collision_mask

    def tick(self):
        simulated_proxy = Roles.simulated_proxy

        for actor, interpolator in self._entity_to_interpolator.items():
            if actor.roles.local != simulated_proxy:
                continue

            actor.physics.world_angular = (0, 0, 0)
            actor.physics.world_velocity = (0, 0, 0)

            try:
                position, orientation = interpolator.next_sample()

            except ValueError:
                continue

            actor.transform.world_position = position
            actor.transform.world_orientation = orientation

    def _update_latency_estimate(self, latency):
        self._latency = latency


def create_network_physics_manager(world):
    if world.netmode == Netmodes.server:
        return ServerNetworkPhysicsManager(world)

    else:
        return ClientNetworkPhysicsManager(world)
