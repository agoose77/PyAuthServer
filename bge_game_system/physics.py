from contextlib import contextmanager

from network.decorators import with_tag
from network.enums import Netmodes, Roles
from network.tagged_delegate import DelegateByNetmode
from network.signals import SignalListener, ReplicableUnregisteredSignal
from network.world_info import WorldInfo

from game_system.entities import Actor
from game_system.controllers import PlayerPawnController
from game_system.enums import PhysicsType
from game_system.latency_compensation import PhysicsExtrapolator
from game_system.signals import *


__all__ = ["BGEPhysicsSystem", "BGEServerPhysics", "BGEClientPhysics"]


class BGEPhysicsSystem(DelegateByNetmode, SignalListener):
    subclasses = {}

    def __init__(self, update_bullet, update_scenegraph):
        self.register_signals()

        self._active_physics = PhysicsType.dynamic, PhysicsType.rigid_body
        self._update_bullet = update_bullet
        self._update_scenegraph = update_scenegraph

    @CopyStateToActor.on_global
    def apply_state(self, state, actor):
        """Copy state information from source to target

        :param state: Source state
        :param actor: Actor to receive state
        """
        actor.transform.world_position = state.position.copy()
        actor.physics.world_velocity = state.velocity.copy()
        actor.physics.world_angular = state.angular.copy()
        actor.transform.world_orientation = state.rotation.copy()
        actor.physics.collision_group = state.collision_group
        actor.physics.collision_mask = state.collision_mask

    @CopyActorToState.on_global
    def dump_state(self, actor, state):
        """Copy state information from source to target

        :param actor: Actor to provide state
        :param state: Dumped state
        """
        state.position = actor.transform.world_position.copy()
        state.velocity = actor.physics.world_velocity.copy()
        state.angular = actor.physics.world_angular.copy()
        state.rotation = actor.transform.world_orientation.copy()
        state.collision_group = actor.physics.collision_group
        state.collision_mask = actor.physics.collision_mask

    @contextmanager
    def protect_exemptions(self, exemptions):
        """Suspend and restore state of exempted actors around an operation

        :param exemptions: Iterable of exempt Actor instances
        """
        # Suspend exempted objects
        skip_updates = set()
        for actor in exemptions:
            physics = actor.physics
            if physics.suspended:
                skip_updates.add(physics)
                continue

            physics.suspended = True

        yield

        # Restore scheduled objects
        for actor in exemptions:
            physics = actor.physics
            if physics in skip_updates:
                continue

            physics.suspended = False

    @PhysicsSingleUpdateSignal.on_global
    def update_for(self, delta_time, target):
        """Listener for PhysicsSingleUpdateSignal
        Attempts to update physics simulation for single actor

        :param delta_time: Time to progress simulation
        :param target: Actor instance to update state"""
        if target.physics.type not in self._active_physics:
            return

        # Make a list of actors which aren't us
        other_actors = [a for a in WorldInfo.subclass_of(Actor) if a is not target] # warning: removed "and a" check here

        with self.protect_exemptions(other_actors):
            self._update_bullet(delta_time)

        self._update_scenegraph()

    @PhysicsTickSignal.on_global
    def update(self, delta_time):
        """Listener for PhysicsTickSignal
        Updates Physics simulation for entire world

        :param delta_time: Time to progress simulation
        """
        self._update_bullet(delta_time)
        self._update_scenegraph()

        UpdateCollidersSignal.invoke()


@with_tag(Netmodes.server)
class BGEServerPhysics(BGEPhysicsSystem):
    """Handles server-side physics"""

    def save_network_states(self):
        """Saves Physics transformations to network variables"""
        for actor in WorldInfo.subclass_of(Actor):
            actor.copy_state_to_network()

    @PhysicsTickSignal.on_global
    def update(self, delta_time):
        """Listener for PhysicsTickSignal.

        Copy physics state to network variable for Actor instances
        """
        super().update(delta_time)

        self.save_network_states()
        UpdateCollidersSignal.invoke()


@with_tag(Netmodes.client)
class BGEClientPhysics(BGEPhysicsSystem):
    """Handles client side physics"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._extrapolators = {}

    def extrapolate_network_states(self):
        """Apply state from extrapolators to replicated actors"""
        simulated_proxy = Roles.simulated_proxy

        controller = PlayerPawnController.get_local_controller()

        if controller is None or controller.info is None:
            return

        network_time = WorldInfo.elapsed + controller.info.ping / 2

        for actor, extrapolator in self._extrapolators.items():
            result = extrapolator.sample_at(network_time)
            if actor.roles.local != simulated_proxy:
                continue

            position, velocity = result

            current_orientation = actor.transform.world_orientation.to_quaternion()
            new_rotation = actor.rigid_body_state.orientation.to_quaternion()
            slerped_orientation = current_orientation.slerp(new_rotation, 0.3)

            actor.transform.world_position = position
            actor.physics.world_velocity = velocity
            actor.transform.world_orientation = slerped_orientation

    @PhysicsReplicatedSignal.on_global
    def on_physics_replicated(self, timestamp, target):
        state = target.rigid_body_state

        position = state.position
        velocity = state.velocity

        try:
            extrapolator = self._extrapolators[target]

        except KeyError:
            extrapolator = PhysicsExtrapolator()
            extrapolator.reset(timestamp, WorldInfo.elapsed, position, velocity)

            self._extrapolators[target] = extrapolator

        extrapolator.add_sample(timestamp, WorldInfo.elapsed, position, velocity, target.transform.world_position)

    @ReplicableUnregisteredSignal.on_global
    def on_replicable_unregistered(self, target):
        if target in self._extrapolators:
            self._extrapolators.pop(target)

    @PhysicsTickSignal.on_global
    def update(self, delta_time):
        """Listener for PhysicsTickSignal.

        Copy physics state to network variable for Actor instances
        """
        super().update(delta_time)

        self.extrapolate_network_states()

        UpdateCollidersSignal.invoke()
