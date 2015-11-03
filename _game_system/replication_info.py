from network.replication import Serialisable
from network.enums import Roles
from network.replicable import Replicable

__all__ = ['AIReplicationInfo', 'PlayerReplicationInfo']


class ReplicationInfo(Replicable):
    pawn = Serialisable(data_type=Replicable)
    roles = Serialisable(Roles(Roles.authority, Roles.simulated_proxy))

    def __init__(self, unique_id, scene, is_static=False):
        self.always_relevant = True

    def can_replicate(self, is_owner, is_initial):
        yield from super().can_replicate(is_owner, is_initial)

        yield "pawn"


class PlayerReplicationInfo(ReplicationInfo):
    name = Serialisable("")
    ping = Serialisable(0.0)

    def can_replicate(self, is_owner, is_initial):
        yield from super().can_replicate(is_owner, is_initial)

        yield "name"
        yield "ping"


