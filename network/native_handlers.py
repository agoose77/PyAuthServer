from .replicables import Replicable, WorldInfo
from .data_struct import Struct
from .descriptors import TypeFlag
from .enums import Roles
from .handler_interfaces import (register_handler, get_handler,
                                 register_description, static_description)
from .serialiser import (handler_from_byte_length, handler_from_bit_length,
                         bits2bytes)
from .bitfield import BitField

from functools import partial
from inspect import signature

__all__ = ['ReplicableTypeHandler', 'RolesHandler', 'ReplicableBaseHandler',
           'StructHandler', 'BitFieldHandler']


def type_description(cls):
    return hash(cls.type_name)


def iterable_description(iterable):
    desc = static_description
    return hash(tuple(desc(x) for x in iterable))


def is_variable_sized(packer):
    size_func = packer.size
    size_signature = signature(size_func)
    parameter_list = list(size_signature.parameters.keys())
    bytes_arg = size_signature.parameters[parameter_list[-1]]
    return bytes_arg.default is bytes_arg.empty


class ReplicableTypeHandler:

    string_packer = get_handler(TypeFlag(str))

    @classmethod
    def pack(cls, cls_):
        return cls.string_packer.pack(cls_.type_name)

    @classmethod
    def unpack_from(cls, bytes_):
        name = cls.string_packer.unpack_from(bytes_)
        return Replicable.from_type_name(name)  # @UndefinedVariable

    @classmethod
    def size(cls, bytes_=None):
        return cls.string_packer.size(bytes_)


class RolesHandler:
    packer = get_handler(TypeFlag(int))

    @classmethod
    def pack(cls, roles):
        pack = cls.packer.pack
        with roles.switched():
            return pack(roles.local) + pack(roles.remote)

    @classmethod
    def unpack_from(cls, bytes_):
        packer = cls.packer
        return Roles(packer.unpack_from(bytes_),
                     packer.unpack_from(bytes_[packer.size():]))

    @classmethod
    def size(cls, bytes_=None):
        return 2 * cls.packer.size()


class IterableHandler:

    iterable_cls = None
    iterable_add = None
    iterable_update = None

    def __init__(self, static_value):
        try:
            element_flag = static_value.data['element_flag']

        except KeyError as err:
            raise TypeError("Unable to pack iterable without\
                             full type information") from err

        self.element_packer = get_handler(element_flag)
        self.count_packer = get_handler(TypeFlag(int))
        self.is_variable_sized = is_variable_sized(self.element_packer)

    def pack(self, iterable):
        element_pack = self.element_packer.pack
        element_count = self.count_packer.pack(len(iterable))
        packed_elements = b''.join(element_pack(x) for x in iterable)
        return element_count + packed_elements

    def unpack_from(self, bytes_):
        size = self.count_packer.unpack_from(bytes_)
        data = bytes_[self.count_packer.size():]
        element_get_size = self.element_packer.size
        element_unpack = self.element_packer.unpack_from

        # Fixed length unpacking
        if not self.is_variable_sized:
            element_size = element_get_size()
            return self.iterable_cls(element_unpack(data[i * element_size:
                                        (i + 1) * element_size])
                                        for i in range(size))

        # Variable length unpacking
        elements = self.iterable_cls()
        add = self.__class__.iterable_add

        for i in range(size):
            shift = element_get_size(data)
            add(elements, element_unpack(data))
            data = data[shift:]

        return elements

    def unpack_merge(self, iterable, bytes_):
        self.__class__.iterable_update(iterable, self.unpack_from(bytes_))

    def size(self, bytes_):
        count_size = self.count_packer.size()
        number_elements = self.count_packer.unpack_from(bytes_)
        data = bytes_[count_size:]
        element_get_size = self.element_packer.size

        if not self.is_variable_sized:
            return (number_elements * element_get_size()) + count_size

        for i in range(number_elements):
            shift = element_get_size(data)
            count_size += shift
            data = data[shift:]

        return count_size


class ListHandler(IterableHandler):
    """Handler for packing list iterables"""
    iterable_cls = list
    iterable_add = list.append

    def list_update(list_, data):
        list_[:] = data

    iterable_update = list_update


class SetHandler(IterableHandler):
    """Handler for packing set iterables"""
    def set_update(set_, data):
        set_.clear()
        set_.update(data)

    iterable_cls = set
    iterable_add = set.add
    iterable_update = set_update


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

    def unpack_from(self, bytes_):
        instance_id = self.unpack_id(bytes_)

        # Return only a replicable that was created by the network
        try:
            replicable = WorldInfo.get_replicable(instance_id)
            return replicable

        except (LookupError):
            print("Couldn't find replicable", instance_id)
            return

    def size(self, bytes_=None):
        return self._packer.size()


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
        struct.read_bytes(bytes_[self.size_packer.size():])

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
    def unpack_from(cls, bytes_):
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

    @classmethod
    def size(cls, bytes_):
        field_size = cls.size_packer.unpack_from(bytes_)
        return bits2bytes(field_size) + cls.size_packer.size()

register_handler(BitField, BitFieldHandler)
register_handler(Roles, RolesHandler)
register_handler(Struct, StructHandler, True)

register_handler(list, ListHandler, True)
register_handler(set, SetHandler, True)

ReplicableHandler = ReplicableBaseHandler()
register_handler(Replicable, ReplicableHandler)
register_handler(type(Replicable), ReplicableTypeHandler)

register_description(type(Replicable), type_description)
register_description(list, iterable_description)
register_description(set, iterable_description)
