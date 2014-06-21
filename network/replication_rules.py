from .replicable import Replicable
from .descriptors import Attribute
from .enums import Roles

__all__ = ['ReplicationRulesBase']


class ReplicationRulesBase(Replicable):
    roles = Attribute(Roles(Roles.authority, Roles.none))

    def pre_initialise(self, addr, netmode):
        raise NotImplementedError

    def post_initialise(self, connection):
        raise NotImplementedError

    def is_relevant(self, conn, replicable):
        raise NotImplementedError
