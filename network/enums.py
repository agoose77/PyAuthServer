from contextlib import contextmanager

from .metaclasses.enumeration import EnumerationMeta

__all__ = ['Enumeration', 'ConnectionStatus', 'Netmodes', 'ConnectionProtocols', 'Roles', 'IterableCompressionType']


class Enumeration(metaclass=EnumerationMeta):
    pass


class ConnectionStatus(Enumeration):
    """Status of connection to peer"""
    values = ("failed", "timeout", "disconnected", "pending", "handshake", "connected")


class Netmodes(Enumeration):
    values = "server", "client"


class ConnectionProtocols(Enumeration):
    values = "request_disconnect", "request_handshake", "handshake_success", "handshake_failed", "replication_init", \
             "replication_del",  "attribute_update", "method_invoke",


class IterableCompressionType(Enumeration):
    values = ("no_compress", "compress", "auto")


class Roles(Enumeration):
    values = ("none", "dumb_proxy", "simulated_proxy", "autonomous_proxy", "authority")

    __slots__ = "local", "remote", "context"

    def __init__(self, local, remote):
        self.local = local
        self.remote = remote
        self.context = False

    def __description__(self):
        return hash((self.context, self.local, self.remote))

    def __repr__(self):
        return "Roles: Local: {}, Remote: {}".format(self.__class__[self.local], self.__class__[self.remote])

    @contextmanager
    def set_context(self, owner):
        self.context = owner

        switched = self.remote == Roles.autonomous_proxy and not owner

        if switched:
            self.remote = Roles.simulated_proxy

        yield

        if switched:
            self.remote = Roles.autonomous_proxy

        self.context = None
