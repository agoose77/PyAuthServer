from network.descriptors import Attribute
from network.enums import Roles
from network.replicable import Replicable

__all__ = ['AIReplicationInfo', 'PlayerReplicationInfo']


class ReplicationInfo(Replicable):
    roles = Attribute(Roles(Roles.authority, Roles.simulated_proxy))

    def on_initialised(self):
        super().on_initialised()

        self.always_relevant = True


class AIReplicationInfo(ReplicationInfo):

    pawn = Attribute(type_of=Replicable, complain=True)

    def conditions(self, is_owner, is_complain, is_initial):
        yield from super().conditions(is_owner, is_complain, is_initial)

        if is_complain:
            yield "pawn"


class PlayerReplicationInfo(AIReplicationInfo):

    name = Attribute("", complain=True)
    ping = Attribute(0.0)

    def conditions(self, is_owner, is_complain, is_initial):
        yield from super().conditions(is_owner, is_complain, is_initial)

        if is_complain:
            yield "name"

        yield "ping"


