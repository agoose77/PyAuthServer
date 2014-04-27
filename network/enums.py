from contextlib import contextmanager

__all__ = ['Enumeration', 'ConnectionStatus', 'Netmodes', 'Protocols', 'Roles']


class Enumeration(type):
    '''Metaclass for Enumerations in Python'''
    def __new__(cls, name, parents, attrs):
        # Get settings
        use_bits = attrs.get('use_bits', False)
        reverse_map = attrs['reverse'] = {}
        # Set the new values
        for index, key in enumerate(attrs["values"]):
            value = index if not use_bits else (2 ** index)
            attrs[key] = value
            reverse_map[value] = key

        # Return new class
        return super().__new__(cls, name, parents, attrs)

    def __getitem__(self, value):
        # Add ability to lookup name
        return self.reverse[value]

    def __contains__(self, index):
        return index in self.reverse

    def __repr__(self):
        return "<Enumeration {}>\n{}\n".format(self.__name__,
                                 '\n'.join("<{}: {}>".format(n, v)
                                   for v, n in self.reverse.items()))


class ConnectionStatus(metaclass=Enumeration):
    values = ("failed", "timeout", "disconnected", "pending", "handshake", "connected")


class Netmodes(metaclass=Enumeration):
    values = "server", "client", "listen", "single"


class HandshakeState(metaclass=Enumeration):
    values = "failure", "success", "request"


class Protocols(metaclass=Enumeration):
    values = ("request_disconnect", "request_handshake",
              "replication_init", "replication_del",
              "replication_update", "method_invoke")


class Roles(metaclass=Enumeration):
    values = ("none", "dumb_proxy", "simulated_proxy",
              "autonomous_proxy", "authority")

    __slots__ = "local", "remote", "context"

    def __init__(self, local, remote):
        self.local = local
        self.remote = remote
        self.context = False

    def __description__(self):
        return hash((self.context, self.local, self.remote))

    def __repr__(self):
        return "Roles: Local: {}, Remote: {}".format(
                                                 self.__class__[self.local],
                                                 self.__class__[self.remote])

    @contextmanager
    def switched(self):
        self.remote, self.local = self.local, self.remote

        if self.local == Roles.autonomous_proxy and not self.context:
            self.local = self.simulated_proxy
            fix_autonomous = True

        else:
            fix_autonomous = False

        yield

        if fix_autonomous:
            self.local = Roles.autonomous_proxy
        self.remote, self.local = self.local, self.remote
