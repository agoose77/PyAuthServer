from contextlib import contextmanager
from collections import defaultdict

from panda3d.bullet import BulletWorld, BulletDebugNode
from panda3d.core import loadPrcFileData
from direct.showbase.DirectObject import DirectObject

from network.annotations.decorators import with_tag
from network.enums import Netmodes, Roles
from network.tagged_delegate import DelegateByNetmode
from network.replicable import Replicable
from network.signals import SignalListener, ReplicableUnregisteredSignal
from _game_system.controllers import PlayerPawnController
from _game_system.entities import Actor
from _game_system.enums import CollisionState, PhysicsType
from _game_system.latency_compensation import PhysicsExtrapolator
from _game_system.physics import CollisionContact, LazyCollisionResult
from _game_system.signals import *
from .definitions import entity_from_nodepath
from .signals import RegisterPhysicsNode, DeregisterPhysicsNode


loadPrcFileData('', 'bullet-enable-contact-events true')

#from panda3d.core import PythonCallbackObject
#loadPrcFileData('', 'bullet-filter-algorithm callback')


class PandaPhysicsSystem(DelegateByNetmode, SignalListener):
    subclasses = {}

    def __init__(self):
        self.register_signals()

        self.world = BulletWorld()
        self.world.setGravity((0, 0, -9.81))

        # # Seems that this does not function
        # on_contact_added = PythonCallbackObject(self._on_contact_added)
        # self.world.set_contact_added_callback(on_contact_added)

        # on_filter = PythonCallbackObject(self._filter_collision)
        # self.world.set_filter_callback(on_filter)

        self.listener = DirectObject()
        self.listener.accept('bullet-contact-added', self._on_contact_added)
        self.listener.accept('bullet-contact-destroyed', self._on_contact_removed)

        debug_node = BulletDebugNode('Debug')
        debug_node.showWireframe(True)
        debug_node.showConstraints(True)
        debug_node.showBoundingBoxes(False)
        debug_node.showNormals(False)

        self.debug_nodepath = render.attachNewNode(debug_node)
        self.world.set_debug_node(debug_node)

        self.tracked_contacts = defaultdict(int)
        self.existing_collisions = set()

    def _create_contacts_from_result(self, requesting_node, contact_result):
        """Return collision contacts between two nodes"""
        contacts = []

        for contact in contact_result.get_contacts():
            if contact.get_node0() == requesting_node:
                manifold = contact.get_manifold_point()

                position = manifold.get_position_world_on_a()
                normal = -manifold.get_normal_world_on_b()

            elif contact.get_node1() == requesting_node:
                manifold = contact.get_manifold_point()

                position = manifold.get_position_world_on_b()
                normal = manifold.get_normal_world_on_b()

            impulse = manifold.get_applied_impulse()
            contact_ = CollisionContact(position, normal, impulse)
            contacts.append(contact_)

        return contacts

    def _on_contact_removed(self, node_a, node_b):
        self.tracked_contacts[(node_a, node_b)] -= 1

    def _on_contact_added(self, node_a, node_b):
        self.tracked_contacts[(node_a, node_b)] += 1

    def _filter_collision(self, filter_data):
        filter_data.set_collide(True)

    @RegisterPhysicsNode.on_global
    def register_node(self, node):
        self.world.attachRigidBody(node)
        node.set_python_tag("world", self.world)

    @DeregisterPhysicsNode.on_global
    def deregister_node(self, node):
        self.world.removeRigidBody(node)
        node.clear_python_tag("world")

    def dispatch_collisions(self):
        # Dispatch collisions
        existing_collisions = self.existing_collisions
        for pair, contact_count in self.tracked_contacts.items():
            if contact_count > 0 and pair not in existing_collisions:
                existing_collisions.add(pair)

                # Dispatch collision
                node_a, node_b = pair

                entity_a = entity_from_nodepath(node_a)
                entity_b = entity_from_nodepath(node_b)

                contact_result = None

                if entity_a is not None:
                    def contact_getter():
                        nonlocal contact_result
                        if contact_result is None:
                            contact_result = self.world.contact_test_pair(node_a, node_b)

                        return self._create_contacts_from_result(node_a, contact_result)

                    collision_result = LazyCollisionResult(entity_b, CollisionState.started, contact_getter)
                    CollisionSignal.invoke(collision_result, target=entity_a)

                if entity_b is not None:
                    def contact_getter():
                        nonlocal contact_result
                        if contact_result is None:
                            contact_result = self.world.contact_test_pair(node_a, node_b)

                        return self._create_contacts_from_result(node_b, contact_result)

                    collision_result = LazyCollisionResult(entity_a, CollisionState.started, contact_getter)
                    CollisionSignal.invoke(collision_result, target=entity_b)

            elif contact_count == 0 and pair in existing_collisions:
                existing_collisions.remove(pair)

                # Dispatch collision
                node_a, node_b = pair

                entity_a = entity_from_nodepath(node_a)
                entity_b = entity_from_nodepath(node_b)

                # Don't send contacts for ended collisions
                contact_getter = lambda: None

                if entity_a is not None:
                    collision_result = LazyCollisionResult(entity_b, CollisionState.ended, contact_getter)
                    CollisionSignal.invoke(collision_result, target=entity_a)

                if entity_b is not None:
                    collision_result = LazyCollisionResult(entity_a, CollisionState.ended, contact_getter)
                    CollisionSignal.invoke(collision_result, target=entity_b)

    def update(self, delta_time):
        self.world.doPhysics(delta_time)
        self.dispatch_collisions()

@with_tag(Netmodes.server)
class PandaServerPhysicsSystem(PandaPhysicsSystem):

    def save_network_states(self):
        """Saves Physics transformations to network variables"""
        for actor in Replicable.subclass_of_type(Actor):
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
class PandaClientPhysicsSystem(PandaPhysicsSystem):
    active_physics_types = {PhysicsType.dynamic, PhysicsType.rigid_body}

    def __init__(self):
        super().__init__()

        self._extrapolators = {}

    @property
    def network_clock(self):
        local_controller = PlayerPawnController.get_local_controller()
        if local_controller is None:
            return

        return local_controller.clock

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
        if target.physics.type not in self.active_physics_types:
            return

        # Make a list of actors which aren't us
        other_actors = Replicable.subclass_of_type(Actor).copy()
        other_actors.discard(target)

        with self.protect_exemptions(other_actors):
            self.world.doPhysics(delta_time)

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
        UpdateCollidersSignal.invoke()