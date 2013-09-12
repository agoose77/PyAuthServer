from .actors import Replicable
from .descriptors import StaticValue, Attribute
from .enums import Roles, Netmodes
from .network import WorldInfo


class BaseGameInfo(Replicable):
    roles = Attribute(
                      Roles(Roles.authority, Roles.none)
                      )

    def pre_initialise(self, addr, netmode):
        return NotImplemented

    def post_initialise(self, connection):
        return NotImplemented

    def on_disconnect(self, replicable):
        return NotImplemented

    def is_relevant(self, conn, replicable):
        return NotImplemented
