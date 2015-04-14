from network.decorators import with_tag
from network.enums import Netmodes
from network.tagged_delegate import DelegateByNetmode
from network.signals import SignalListener
from network.world_info import WorldInfo

from game_system.entities import Actor
from game_system.signals import *


class PandaPhysicsSystem(DelegateByNetmode, SignalListener):
    subclasses = {}

    def __init__(self):
        self.register_signals()


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
        self.save_network_states()
        UpdateCollidersSignal.invoke()