from contextlib import contextmanager

from .metaclasses.enumeration import EnumerationMeta

__all__ = ['Enum', 'ConnectionStates', 'Netmodes', 'PacketProtocols', 'Roles', 'IterableCompressionType']


class _EnumDict(dict):

    def __init__(self, autonum):
        super().__init__()

        self._member_names = []
        self._autonum = autonum
        self._has_real_values = False

    def __setitem__(self, name, value):
        if name.startswith("__"):
            return super().__setitem__(name, value)

        if name in self._member_names:
            raise ValueError("'{}' is already a member of '{}' Enum".format(name, self.__class__.__name__))

        # Auto numbering
        if value is Ellipsis:
            if self._has_real_values:
                raise SyntaxError("An implicit definition cannot follow an explicit one")

            value = self._autonum(len(self._member_names))

        # Int values
        elif isinstance(value, int):
            if self._member_names and not self._has_real_values:
                print(self._member_names, value)
                raise SyntaxError("An explicit definition cannot follow an implicit one")

            self._has_real_values = True

        else:
            super().__setitem__(name, value)

        self._member_names.append(name)
        super().__setitem__(name, value)


def default_numbering(i):
    return i


class EnumerationMeta(type):
    """Metaclass for Enumerations in Python"""

    def __init__(metacls, name, bases, namespace, autonum=None):
        super().__init__(name, bases, namespace)

    def __new__(metacls, name, bases, namespace, autonum=None):
        identifiers = namespace._member_names

        # Return new class
        cls = super().__new__(metacls, name, bases, namespace)

        cls.identifiers = tuple(identifiers)
        cls._values_to_identifiers = {namespace[n]: n for n in identifiers}

        return cls

    @classmethod
    def __prepare__(metacls, name, bases, autonum=default_numbering, **kwargs):
        return _EnumDict(autonum)

    def __getitem__(cls, value):
        # Add ability to lookup name
        return cls._values_to_identifiers[value]

    def __contains__(cls, value):
        return value in cls._values_to_identifiers

    def __len__(cls):
        return len(cls.identifiers)

    def __iter__(cls):
        namespace = cls.__dict__
        return ((k, namespace[k]) for k in cls.identifiers)


class Enum(metaclass=EnumerationMeta):
    pass


class ConnectionStates(Enum):
    """Status of connection to peer"""
    failed = ...
    timeout = ...
    disconnected = ...
    init = ...
    awaiting_handshake = ...
    received_handshake = ...
    connected = ...


class Netmodes(Enum):
    server = ...
    client = ...


class PacketProtocols(Enum):
    heartbeat = ...
    request_disconnect = ...
    invoke_handshake = ...
    request_handshake = ...
    handshake_success = ...
    handshake_failed = ...
    create_scene = ...
    delete_scene = ...

    # Replication
    create_replicable = ...
    delete_replicable = ...
    update_attributes = ...
    invoke_method = ...


class IterableCompressionType(Enum):
    no_compress = ...
    compress = ...
    auto = ...


class Roles(Enum):
    none = ...
    dumb_proxy = ...
    simulated_proxy = ...
    autonomous_proxy = ...
    authority = ...

    __slots__ = "local", "remote", "_context"

    def __init__(self, local, remote):
        self.local = local
        self.remote = remote
        self._context = None

    def __description__(self):
        return hash((self._context, self.local, self.remote))

    def __repr__(self):
        return "Roles: Local: {}, Remote: {}".format(self.__class__[self.local],
                                                     self.__class__[self.remote])

    @contextmanager
    def set_context(self, is_owner):
        self._context = is_owner

        if self.remote == Roles.autonomous_proxy and not is_owner:
            self.remote = Roles.simulated_proxy
            yield
            self.remote = Roles.autonomous_proxy

        else:
            yield

        self._context = None
