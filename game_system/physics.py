from collections import defaultdict

from network.decorators import with_tag
from network.enums import Netmodes, Roles
from network.tagged_delegate import DelegateByNetmode
from network.signals import SignalListener, ReplicableUnregisteredSignal
from network.world_info import WorldInfo

from .entities import Actor
from .controllers import PlayerController
from .coordinates import Vector
from .enums import PhysicsType
from .signals import *


__all__ = ["PhysicsSystem", "ServerPhysics", "ClientPhysics", "EPICExtrapolator"]


# HANDLE NETMODE DELEGATION AND ENV DELEGATION
class PhysicsSystem(DelegateByNetmode, SignalListener):
    subclasses = {}

    def __init__(self):
        self.register_signals()

        self._active_physics = PhysicsType.dynamic, PhysicsType.rigid_body

    @CopyStateToActor.global_listener
    def copy_to_actor(self, state, actor):
        """Copy state information from source to target

        :param source_state: State to copy from
        :param target_state: State to copy to"""
        actor.transform.world_position = state.position.copy()
        actor.physics.world_velocity = state.velocity.copy()
        actor.physics.world_angular = state.angular.copy()
        actor.transform.world_orientation = state.rotation.copy()
        actor.physics.collision_group = state.collision_group
        actor.physics.collision_mask = state.collision_mask

    @CopyActorToState.global_listener
    def copy_to_state(self, actor, state):
        """Copy state information from source to target

        :param source_state: State to copy from
        :param target_state: State to copy to
        """
        state.position = actor.transform.world_position.copy()
        state.velocity = actor.physics.world_velocity.copy()
        state.angular = actor.physics.world_angular.copy()
        state.rotation = actor.transform.world_orientation.copy()
        state.collision_group = actor.physics.collision_group
        state.collision_mask = actor.physics.collision_mask


@with_tag(Netmodes.server)
class ServerPhysics(PhysicsSystem):

    def save_network_states(self):
        """Saves Physics transformations to network variables"""
        for replicable in WorldInfo.subclass_of(Actor):
            replicable.copy_state_to_network()

    @PhysicsTickSignal.global_listener
    def update(self, delta_time):
        """Listener for PhysicsTickSignal.

        Copy physics state to network variable for Actor instances
        """
        self.save_network_states()


@with_tag(Netmodes.client)
class ClientPhysics(PhysicsSystem):

    def __init__(self):
        super().__init__()

        self._extrapolators = defaultdict(EPICExtrapolator)

    def extrapolate_network_states(self):
        """Apply state from extrapolators to replicated actors"""
        simulated_proxy = Roles.simulated_proxy

        controller = PlayerController.get_local_controller()
        network_time = WorldInfo.elapsed + controller.info.ping / 2

        for actor, extrapolator in self._extrapolators.items():
            result = extrapolator.sample_at(network_time)

            if actor.roles.local != simulated_proxy:
                continue

            position, velocity = result

            actor.transform.world_position = position
            actor.physics.world_velocity = velocity

    @PhysicsReplicatedSignal.global_listener
    def on_physics_replicated(self, timestamp, position, velocity, target):
        extrapolator = self._extrapolators[target]
        extrapolator.add_sample(timestamp, WorldInfo.elapsed, target.transform.world_position, position, velocity)

    @ReplicableUnregisteredSignal.global_listener
    def on_replicable_unregistered(self, target):
        if target in self._extrapolators:
            self._extrapolators.pop(target)

    @PhysicsTickSignal.global_listener
    def update(self, delta_time):
        """Listener for PhysicsTickSignal.

        Copy physics state to network variable for Actor instances
        """

        self.extrapolate_network_states()


class EPICExtrapolator:

    MINIMUM_DT = 0.01

    def __init__(self):
        self._update_time = 0.0
        self._last_timestamp = 0.0
        self._snap_timestamp = 0.0
        self._target_timestamp = 0.0

        self._snap_position = Vector()
        self._target_position = Vector()
        self._snap_velocity = Vector()
        self._last_position = Vector()

    def add_sample(self, timestamp, current_time, current_position, position, velocity=None):
        """Add new sample to the extrapolator

        :param timestamp: timestamp of new sample
        :param current_time: timestamp sample was received
        :param current_position: position at current time
        :param position: position of new sample
        :param velocity: velocity of new sample
        """
        if velocity is None:
            velocity = self.determine_mean_velocity(timestamp, position)

        if timestamp <= self._last_timestamp:
            return

        position = position.copy()
        velocity = velocity.copy()

        self.update_estimates(timestamp)

        self._last_position = position
        self._last_timestamp = timestamp

        self._snap_position = current_position.copy()
        self._snap_timestamp = current_time

        self._target_timestamp = current_time + self._update_time

        delta_time = self._target_timestamp - timestamp
        self._target_position = position + velocity * delta_time

        if abs(self._target_timestamp - self._snap_timestamp) < self.__class__.MINIMUM_DT:
            self._snap_velocity = velocity

        else:
            delta_time = 1.0 / (self._target_timestamp - self._snap_timestamp)
            self._snap_velocity = (self._target_position - self._snap_position) * delta_time

    def determine_mean_velocity(self, timestamp, position):
        """Determine velocity required to move to a given position with respect to the delta time

        :param timestamp: timestamp of new position
        :param position: target position
        """
        if abs(timestamp - self._last_timestamp) > self.__class__.MINIMUM_DT:
            delta_time = 1.0 / (timestamp - self._last_timestamp)
            velocity = (position - self._last_position) * delta_time

        else:
            velocity = Vector()

        return velocity

    def sample_at(self, request_time):
        """Sample the extrapolator for timestamp

        :param request_time: timestamp of sample
        """
        max_timestamp = self._target_timestamp + self._update_time

        valid = True
        if request_time < self._snap_timestamp:
            request_time = self._snap_timestamp
            valid = False

        if request_time > max_timestamp:
            request_time = max_timestamp
            valid = False

        velocity = self._snap_velocity.copy()
        position = self._snap_position + velocity * (request_time - self._snap_timestamp)

        if not valid:
            velocity.zero()

        return position, velocity

    def reset(self, timestamp, current_time, position, velocity):
        """Ignore previous samples and base extrapolator upon new data

        :param timestamp: timestamp of base sample
        :param current_time: current timestamp
        :param position: position of base sample
        :param velocity: velocity of base sample
        """
        assert timestamp <= current_time
        self._last_timestamp = timestamp
        self._last_position = position
        self._snap_timestamp = current_time
        self._snap_position = position
        self._update_time = current_time - timestamp
        self._target_timestamp = current_time + self._update_time
        self._snap_velocity = velocity
        self._target_position = position + velocity * self._update_time

    def update_estimates(self, timestamp):
        """Update extrapolator estimate of the update time

        :param timestamp: timestamp of new sample
        """
        update_time = timestamp - self._last_timestamp
        if update_time > self._update_time:
            self._update_time = (self._update_time + update_time) * 0.5

        else:
            self._update_time = (self._update_time * 7 + update_time) * 0.125