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


__all__ = ["BlenderPhysicsSystem", "BlenderEServerPhysics", "BlenderClientPhysics"]


class BlenderPhysicsSystem(DelegateByNetmode, SignalListener):
    subclasses = {}

    def __init__(self):
        self.register_signals()

        self._active_physics = PhysicsType.dynamic, PhysicsType.rigid_body
        print("PHYS STYS")

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

    @PhysicsTickSignal.on_global
    def update(self, delta_time):
        """Listener for PhysicsTickSignal
        Updates Physics simulation for entire world

        :param delta_time: Time to progress simulation
        """
        UpdateCollidersSignal.invoke()


@with_tag(Netmodes.server)
class BlenderServerPhysics(BlenderPhysicsSystem):
    """Handles server-side physics"""

    def save_network_states(self):
        """Saves Physics transformations to network variables"""
  #      print(list(Actor), WorldInfo.subclass_of(Actor))
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
class BlenderClientPhysics(BlenderPhysicsSystem):
    """Handles client side physics"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._extrapolators = {}

    @property
    def network_clock(self):
        local_controller = PlayerPawnController.get_local_controller()
        if local_controller is None:
            return

        return local_controller.clock

    @contextmanager
    def protect_exemptions(self, exemptions):
        """Suspend and restore state of exempted actors around an operation

        :param exemptions: Iterable of exempt Actor instances
        """
        # Suspend exempted objects
        already_suspended = set()

        for actor in exemptions:
            physics = actor.physics

            if physics.suspended:
                already_suspended.add(physics)
                continue

            physics.suspended = True

        yield

        # Restore scheduled objects
        for actor in exemptions:
            physics = actor.physics
            if physics in already_suspended:
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
        other_actors = WorldInfo.subclass_of(Actor).copy()
        other_actors.discard(target)

    def extrapolate_network_states(self):
        """Apply state from extrapolators to replicated actors"""
        simulated_proxy = Roles.simulated_proxy

        clock = self.network_clock
        if clock is None:
            return

        network_time = clock.estimated_elapsed_server

        for actor, extrapolator in self._extrapolators.items():
            result = extrapolator.sample_at(network_time)
            if actor.roles.local != simulated_proxy:
                continue

            position, velocity = result

            current_orientation = actor.transform.world_orientation.to_quaternion()
            new_rotation = actor.rigid_body_state.orientation.to_quaternion()
            slerped_orientation = current_orientation.slerp(new_rotation, 0.3).to_euler()

            actor.transform.world_position = position
            actor.physics.world_velocity = velocity
            actor.transform.world_orientation = slerped_orientation

    @PhysicsReplicatedSignal.on_global
    def on_physics_replicated(self, timestamp, target):
        state = target.rigid_body_state

        position = state.position
        velocity = state.velocity

        clock = self.network_clock

        if clock is None:
            return

        network_time = clock.estimated_elapsed_server

        try:
            extrapolator = self._extrapolators[target]

        except KeyError:
            extrapolator = PhysicsExtrapolator()
            extrapolator.reset(timestamp, network_time, position, velocity)

            self._extrapolators[target] = extrapolator

        extrapolator.add_sample(timestamp, network_time, position, velocity)

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
        print("CLIEYUOP")
        UpdateCollidersSignal.invoke()
