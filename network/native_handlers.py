from .replicables import Replicable, WorldInfo
from .data_struct import Struct
from .descriptors import TypeFlag
from .enums import Roles
from .handler_interfaces import (register_handler, get_handler,
                                 register_description)
from .serialiser import (handler_from_byte_length, handler_from_bit_length,
                         bits2bytes)
from .bitfield import BitField

__all__ = ['ReplicableTypeHandler', 'RolesHandler', 'ReplicableBaseHandler',
           'StructHandler', 'BitFieldHandler']


def type_description(cls):
    return hash(cls.type_name)


class ReplicableTypeHandler:

    string_packer = get_handler(TypeFlag(str))

    @classmethod
    def pack(cls, cls_):
        return cls.string_packer.pack(cls_.type_name)

    @classmethod
    def unpack(cls, bytes_):
        name = cls.string_packer.unpack_from(bytes_)
        return Replicable.from_type_name(name)  # @UndefinedVariable

    @classmethod
    def size(cls, bytes_=None):
        return cls.string_packer.size(bytes_)

    unpack_from = unpack


class RolesHandler:
    packer = get_handler(TypeFlag(int))

    @classmethod
    def pack(cls, roles):
        pack = cls.packer.pack
        with roles.switched():
            return pack(roles.local) + pack(roles.remote)

    @classmethod
    def unpack(cls, bytes_):
        packer = cls.packer
        return Roles(packer.unpack_from(bytes_),
                     packer.unpack_from(bytes_[packer.size():]))

    @classmethod
    def size(cls, bytes_=None):
        return 2 * cls.packer.size()

    unpack_from = unpack


class ReplicableBaseHandler:
    """Handler for packing replicable proxy
    Packs replicable references and unpacks to proxy OR reference"""

    def __init__(self):
        self._packer = get_handler(TypeFlag(int,
                                   max_value=self.maximum_replicables))

    @property
    def maximum_replicables(self):
        return Replicable._MAXIMUM_REPLICABLES

    @maximum_replicables.setter
    def maximum_replicables(self, value):
        Replicable._MAXIMUM_REPLICABLES = value

        self._packer = get_handler(TypeFlag(int, max_value=value))

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
            return replicable

        except (LookupError):
            print("Couldn't find replicable", list(Replicable), instance_id)
            return

    def size(self, bytes_=None):
        return self._packer.size(bytes_)

    unpack_from = unpack


class StructHandler:

    def __init__(self, static_value):
        self.struct_cls = static_value.type
        self.size_packer = get_handler(TypeFlag(int))

    def pack(self, struct):
        bytes_ = struct.to_bytes()
        return self.size_packer.pack(len(bytes_)) + bytes_

    def unpack_from(self, bytes_):
        struct = self.struct_cls()
        self.unpack_merge(struct, bytes_)
        return struct

    def unpack_merge(self, struct, bytes_):
        struct.from_bytes(bytes_[self.size_packer.size():])

    def size(self, bytes_):
        return self.size_packer.unpack_from(bytes_) + self.size_packer.size()


class BitFieldHandler:

    size_packer = get_handler(TypeFlag(int))

    @classmethod
    def pack(cls, field):
        # Get the smallest needed packer for this bitfield
        footprint = field.footprint
        packed_size = cls.size_packer.pack(field._size)

        if footprint:
            field_packer = handler_from_byte_length(footprint)
            return packed_size + field_packer.pack(field._value)
        else:
            return packed_size

    @classmethod
    def unpack(cls, bytes_):
        field_size = cls.size_packer.unpack_from(bytes_)

        if field_size:
            field_packer = handler_from_bit_length(field_size)
            data = field_packer.unpack_from(bytes_[cls.size_packer.size():])
        else:
            data = 0

        field = BitField(field_size, data)
        return field

    @classmethod
    def unpack_merge(cls, field, bytes_):
        footprint = field.footprint
        if footprint:
            field_packer = handler_from_byte_length(footprint)
            field._value = field_packer.unpack_from(
                                bytes_[cls.size_packer.size():])

    unpack_from = unpack

    @classmethod
    def size(cls, bytes_):
        field_size = cls.size_packer.unpack_from(bytes_)
        return bits2bytes(field_size) + cls.size_packer.size()

register_handler(BitField, BitFieldHandler)
register_handler(Roles, RolesHandler)
register_handler(Struct, StructHandler, True)

ReplicableHandler = ReplicableBaseHandler()
register_handler(Replicable, ReplicableHandler)
register_handler(type(Replicable), ReplicableTypeHandler)
register_description(type(Replicable), type_description)
