from collections import defaultdict
from contextlib import contextmanager

from network.decorators import with_tag
from network.enums import Netmodes, Roles
from network.tagged_delegate import DelegateByNetmode
from network.signals import SignalListener, ReplicableUnregisteredSignal
from network.world_info import WorldInfo

from game_system.entities import Actor
from game_system.controllers import PlayerController
from game_system.enums import PhysicsType
from game_system.physics import PhysicsSystem,EPICExtrapolator
from game_system.signals import *


__all__ = ["BGEPhysicsSystem", "BGEServerPhysics", "BGEClientPhysics"]


@with_tag("BGE")
class BGEPhysicsSystem(DelegateByNetmode, PhysicsSystem, SignalListener):
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

    @contextmanager
    def protect_exemptions(self, exemptions):
        """Suspend and restore state of exempted actors around an operation

        :param exemptions: Iterable of exempt Actor instances"""
        # Suspend exempted objects
        skip_updates = set()
        for actor in exemptions:
            if actor.suspended:
                skip_updates.add(actor)
                continue
            actor.suspended = True

        yield

        # Restore scheduled objects
        for actor in exemptions:
            if actor in skip_updates:
                continue

            actor.suspended = False

    @PhysicsSingleUpdateSignal.global_listener
    def update_for(self, delta_time, target):
        """Listener for PhysicsSingleUpdateSignal
        Attempts to update physics simulation for single actor

        :param delta_time: Time to progress simulation
        :param target: Actor instance to update state"""
        if not target.physics in self._active_physics:
            return

        # Make a list of actors which aren't us
        other_actors = [a for a in WorldInfo.subclass_of(Actor)
                        if a != target and a]

        with self.protect_exemptions(other_actors):
            self._update_func(delta_time)
        self._apply_func()

    @PhysicsTickSignal.global_listener
    def update(self, delta_time):
        """Listener for PhysicsTickSignal
        Updates Physics simulation for entire world

        :param delta_time: Time to progress simulation
        """
        self._update_func(delta_time)
        self._apply_func()

        UpdateCollidersSignal.invoke()


@with_tag(Netmodes.server)
class BGEServerPhysics(BGEPhysicsSystem):

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
        UpdateCollidersSignal.invoke()


@with_tag(Netmodes.client)
class BGEClientPhysics(BGEPhysicsSystem):

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
        UpdateCollidersSignal.invoke()
        print("EX")
