from network.decorators import with_tag
from network.enums import Netmodes
from network.tagged_delegate import DelegateByNetmode
from network.signals import SignalListener
from network.world_info import WorldInfo

from game_system.entities import Actor
from game_system.signals import *

from .signals import RegisterPhysicsNode, DeregisterPhysicsNode
from panda3d.bullet import BulletWorld
from panda3d.core import PythonCallbackObject
from direct.showbase.DirectObject import DirectObject


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

    def _on_contact_added(self, node_a, node_b):
        if node_a.has_python_tag("on_contact_added"):
            callback = node_a.get_python_tag("on_contact_added")
            callback(node_b)

        if node_b.has_python_tag("on_contact_added"):
            callback = node_b.get_python_tag("on_contact_added")
            callback(node_a)

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