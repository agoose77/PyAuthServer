from contextlib import contextmanager

__all__ = ['Enumeration', 'ConnectionStatus', 'Netmodes', 'Protocols', 'Roles', 'IterableCompressionType']


class Enumeration(type):
    """Metaclass for Enumerations in Python"""

    def __new__(cls, name, parents, attrs):
        # Get settings
        get_index = (lambda x: 2 ** x if attrs.get('use_bits', False) else x)

        values = attrs['values']

        forward_mapping = {v: get_index(i) for i, v in enumerate(values)}
        reverse_mapping = {i: v for v, i in forward_mapping.items()}

        attrs.update(forward_mapping)
        attrs['keys_to_values'] = forward_mapping
        attrs['values_to_keys'] = reverse_mapping

        # Return new class
        return super().__new__(cls, name, parents, attrs)

    def __getitem__(self, value):
        # Add ability to lookup name
        return self.values_to_keys[value]

    def __contains__(self, index):
        return index in self.values_to_keys

    def __repr__(self):
        contents_string = '\n'.join("<{}: {}>".format(*mapping) for mapping in self.keys_to_values.items())
        return "<Enumeration {}>\n{}\n".format(self.__name__, contents_string)


class ConnectionStatus(metaclass=Enumeration):
    values = ("failed", "timeout", "disconnected", "pending", "handshake", "connected")


class Netmodes(metaclass=Enumeration):
    values = "server", "client"


class HandshakeState(metaclass=Enumeration):
    values = "failure", "success", "request"


class Protocols(metaclass=Enumeration):
    values = ("request_disconnect", "request_handshake", "replication_init", "replication_del",  "replication_update",
              "method_invoke")


class IterableCompressionType(metaclass=Enumeration):
    values = ("no_compress", "compress", "auto")


class Roles(metaclass=Enumeration):
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
