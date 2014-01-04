from .replicables import Replicable
from .descriptors import Attribute
from .enums import Roles

__all__ = ['ReplicationRules']


class ReplicationRules(Replicable):
    roles = Attribute(
                      Roles(Roles.authority, Roles.none)  # @UndefinedVariable
                      )

    def pre_initialise(self, addr, netmode):
        raise NotImplementedError

    def post_initialise(self, connection):
        raise NotImplementedError

    def on_disconnect(self, replicable):
        raise NotImplementedError

    def is_relevant(self, conn, replicable):
        raise NotImplementedError
