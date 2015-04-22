from network.decorators import with_tag
from network.enums import Netmodes, Roles
from network.tagged_delegate import DelegateByNetmode
from network.signals import SignalListener, ReplicableUnregisteredSignal
from network.world_info import WorldInfo

from game_system.controllers import PlayerPawnController
from game_system.entities import Actor
from game_system.latency_compensation import PhysicsExtrapolator
from game_system.physics import CollisionContact
from game_system.signals import *

from .signals import RegisterPhysicsNode, DeregisterPhysicsNode

from panda3d.bullet import BulletWorld
from panda3d.core import loadPrcFileData
from direct.showbase.DirectObject import DirectObject
#from panda3d.core import PythonCallbackObject

loadPrcFileData('', 'bullet-enable-contact-events true')
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

    def _get_contacts(self, node):
        test = self.world.contact_test(node)
        contacts = []

        for contact in test.get_contacts():
            if contact.get_node0() == node:
                manifold = contact.get_manifold_point()

                position = manifold.get_position_world_on_a()
                normal = None

            elif contact.get_node1() == node:
                manifold = contact.get_manifold_point()

                position = manifold.get_position_world_on_b()
                normal = None

            else:
                continue

            impulse = manifold.get_applied_impulse()
            contact_ = CollisionContact(position, normal, impulse)
            contacts.append(contact_)

        return contacts

    def _on_contact_added(self, node_a, node_b):
        if node_a.has_python_tag("on_contact_added"):
            callback = node_a.get_python_tag("on_contact_added")

            contacts = self._get_contacts(node_a)
            callback(node_b, contacts)

        if node_b.has_python_tag("on_contact_added"):
            callback = node_b.get_python_tag("on_contact_added")

            contacts = self._get_contacts(node_b)
            callback(node_a, contacts)

    def _on_contact_removed(self, node_a, node_b):
        if node_a.has_python_tag("on_contact_removed"):
            callback = node_a.get_python_tag("on_contact_removed")
            callback(node_b)

        if node_b.has_python_tag("on_contact_removed"):
            callback = node_b.get_python_tag("on_contact_removed")
            callback(node_a)

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

    def update(self, delta_time):
        self.world.doPhysics(delta_time)


@with_tag(Netmodes.server)
class PandaServerPhysicsSystem(PandaPhysicsSystem):

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
class PandaClientPhysicsSystem(PandaPhysicsSystem):

    def __init__(self):
        super().__init__()

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