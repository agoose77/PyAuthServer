from network.decorators import with_tag
from network.enums import Netmodes
from network.tagged_delegate import DelegateByNetmode
from network.signals import SignalListener
from network.world_info import WorldInfo

from game_system.entities import Actor
from game_system.signals import *

from .signals import RegisterPhysicsNode, DeregisterPhysicsNode
from panda3d.bullet import BulletWorld


class PandaPhysicsSystem(DelegateByNetmode, SignalListener):
    subclasses = {}

    def __init__(self):
        self.register_signals()

        self.world = BulletWorld()
        self.world.setGravity((0, 0, -9.81))

    @RegisterPhysicsNode.on_global
    def register_node(self, node):
        self.world.attachRigidBody(node)
        print("ATTACH")

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