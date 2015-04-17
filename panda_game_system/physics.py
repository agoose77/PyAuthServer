from network.decorators import with_tag
from network.enums import Netmodes
from network.tagged_delegate import DelegateByNetmode
from network.signals import SignalListener
from network.world_info import WorldInfo

from game_system.coordinates import Vector
from game_system.entities import Actor
from game_system.physics import CollisionContact
from game_system.signals import *

from .signals import RegisterPhysicsNode, DeregisterPhysicsNode

from panda3d.bullet import BulletWorld
from direct.showbase.DirectObject import DirectObject
#from panda3d.core import PythonCallbackObject


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

    @DeregisterPhysicsNode.on_global
    def deregister_node(self, node):
        self.world.removeRigidBody(node)

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