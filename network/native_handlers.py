from .actors import Replicable, WorldInfo
from .descriptors import StaticValue
from .enums import Roles
from .handler_interfaces import (register_handler, get_handler,
                                 register_description)
from .proxy import ReplicableProxy
from .registers import TypeRegister

from weakref import proxy as weak_proxy


class TypeHandler:

    def __init__(self, static_value):
        self.base_type = Replicable
        self.string_packer = get_handler(StaticValue(str))

    def pack(self, cls):
        return self.string_packer.pack(cls.type_name)

    def unpack(self, bytes_):
        name = self.string_packer.unpack_from(bytes_)
        cls = self.base_type.from_type_name(name)
        return cls

    def size(self, bytes_=None):
        return self.string_packer.size(bytes_)

    unpack_from = unpack


def type_description(cls):
    return hash(cls.type_name)


class RolesHandler:
    packer = get_handler(StaticValue(int))

    @classmethod
    def pack(cls, roles):
        with roles.switched():
            return cls.packer.pack(roles.local) + cls.packer.pack(roles.remote)

    @classmethod
    def unpack(cls, bytes_):
        return Roles(cls.packer.unpack(bytes_), cls.packer.unpack(bytes_[1:]))

    @classmethod
    def size(cls, bytes_=None):
        return 2 * cls.packer.size()

    unpack_from = unpack


class ReplicableProxyBaseHandler:
    """Handler for packing replicable proxy
    Packs replicable references and unpacks to proxy OR reference"""

    def __init__(self):
        self._maximum_replicables = 255
        self._packer = get_handler(StaticValue(int,
                                   max_value=self._maximum_replicables))

    @property
    def maximum_replicables(self):
        return self._maximum_replicables

    @maximum_replicables.setter
    def maximum_replicables(self, value):
        self._maximum_replicables = value
        self._packer = get_handler(StaticValue(int, max_value=value))

    def pack(self, replicable):
        # Send the instance ID
        return self.pack_id(replicable.instance_id)

    def pack_id(self, id_):
        return self._packer.pack(id_)

    def unpack_id(self, bytes_):
        return self._packer.unpack_from(bytes_)

    def unpack(self, bytes_):
        instance_id = self.unpack_id(bytes_)

        # Return only a replicable that was created by the network
        try:
            replicable = WorldInfo.get_replicable(instance_id)
            # Check that it was made locally and has a remote role
            # replicable.roles.remote != Roles.none
            assert replicable._local_authority
            return replicable

        # We can't be sure that this is the correct instance
        # Use proxy to delay checks
        # Also, in past revisions: hoping it will have now been replicated
        except (LookupError, AssertionError):
            return ReplicableProxy(instance_id)

    def size(self, bytes_=None):
        return self._packer.size(bytes_)

    unpack_from = unpack

ReplicableProxyHandler = ReplicableProxyBaseHandler()

register_handler(TypeRegister, TypeHandler, True)
register_handler(Roles, RolesHandler)
register_handler(Replicable, ReplicableProxyHandler)

register_description(TypeRegister, type_description)
