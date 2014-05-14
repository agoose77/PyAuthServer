from .bitfield import BitField
from .descriptors import TypeFlag
from .enums import Roles
from .handler_interfaces import *
from .iterators import partition_iterable
from .replicable import Replicable
from .serialiser import *
from .world_info import WorldInfo

from inspect import signature

__all__ = ['ReplicableTypeHandler', 'RolesHandler', 'ReplicableBaseHandler',
           'StructHandler', 'FixedBitFieldHandler', 'VariableBitFieldHandler',
           'type_description', 'iterable_description', 'is_variable_sized',
           'bitfield_selector']


def type_description(cls):
    return hash(cls.type_name)


def iterable_description(iterable):
    return hash(tuple(iterable))


def is_variable_sized(packer):
    size_func = packer.size
    size_signature = signature(size_func)
    parameter_list = list(size_signature.parameters.keys())
    bytes_stringarg = size_signature.parameters[parameter_list[-1]]
    return bytes_stringarg.default is bytes_stringarg.empty


class ReplicableTypeHandler:

    string_packer = get_handler(TypeFlag(str))

    @classmethod
    def pack(cls, cls_):
        return cls.string_packer.pack(cls_.type_name)

    @classmethod
    def unpack_from(cls, bytes_string):
        name = cls.string_packer.unpack_from(bytes_string)
        return Replicable.from_type_name(name)  # @UndefinedVariable

    @classmethod
    def size(cls, bytes_string=None):
        return cls.string_packer.size(bytes_string)


class RolesHandler:
    packer = get_handler(TypeFlag(int))

    @classmethod
    def pack(cls, roles):
        """Pack roles for client
        Switches remote and local roles

        :param roles: role enum
        :returms: packed roles (bytes)"""
        pack = cls.packer.pack
        return pack(roles.remote) + pack(roles.local)

    @classmethod
    def unpack_from(cls, bytes_string):
        packer = cls.packer
        return Roles(packer.unpack_from(bytes_string),
                     packer.unpack_from(bytes_string[packer.size():]))

    @classmethod
    def size(cls, bytes_string=None):
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

        int_flag = TypeFlag(int)

        self.element_packer = get_handler(element_flag)
        self.count_packer = get_handler(int_flag)
        self.is_variable_sized = is_variable_sized(self.element_packer)

    def pack(self, iterable):
        element_pack = self.element_packer.pack
        element_count = self.count_packer.pack(len(iterable))
        packed_elements = b''.join(element_pack(x) for x in iterable)
        return element_count + packed_elements

    def unpack_from(self, bytes_string):
        size = self.count_packer.unpack_from(bytes_string)
        data = bytes_string[self.count_packer.size():]
        element_get_size = self.element_packer.size
        element_unpack = self.element_packer.unpack_from

        # Fixed length unpacking
        if not self.is_variable_sized:
            element_size = element_get_size()
            partitioned_iterable = partition_iterable(data, element_size, size)
            return self.iterable_cls(partitioned_iterable)

        # Variable length unpacking
        elements = self.iterable_cls()
        add = self.__class__.iterable_add

        for _ in range(size):
            shift = element_get_size(data)
            add(elements, element_unpack(data))
            data = data[shift:]

        return elements

    def unpack_merge(self, iterable, bytes_string):
        self.__class__.iterable_update(iterable, self.unpack_from(bytes_string))

    def size(self, bytes_string):
        count_size = self.count_packer.size()
        number_elements = self.count_packer.unpack_from(bytes_string)
        data = bytes_string[count_size:]
        element_get_size = self.element_packer.size

        if not self.is_variable_sized:
            return (number_elements * element_get_size()) + count_size

        # Account for variable sized elements
        for i in range(number_elements):
            shift = element_get_size(data)
            count_size += shift
            data = data[shift:]

        return count_size


class ListHandler(IterableHandler):
    """Handler for packing list iterables"""
    iterable_cls = list
    iterable_add = list.append

    def iterable_update(list_, data):  # @NoSelf
        list_[:] = data


class SetHandler(IterableHandler):
    """Handler for packing set iterables"""
    iterable_cls = set
    iterable_add = set.add

    def iterable_update(set_, data):  # @NoSelf
        set_.clear()
        set_.update(data)


class ReplicableBaseHandler:
    """Handler for packing replicable proxy
    Packs replicable references and unpacks to proxy OR reference"""

    def __init__(self):
        id_flag = TypeFlag(int, max_value=Replicable._MAXIMUM_REPLICABLES)
        self._packer = get_handler(id_flag)

    def pack(self, replicable):
        # Send the instance ID
        return self.pack_id(replicable.instance_id)

    def pack_id(self, id_):
        return self._packer.pack(id_)

    def unpack_id(self, bytes_string):
        return self._packer.unpack_from(bytes_string)

    def unpack_from(self, bytes_string):
        instance_id = self.unpack_id(bytes_string)

        # Return only a replicable that was created by the network

        try:
            replicable = WorldInfo.get_replicable(instance_id)
            return replicable

        except (LookupError):
            print("ReplicableBaseHandler: Couldn't find replicable with ID "\
                  "'{}'".format(instance_id))
            return

    def size(self, bytes_string=None):
        return self._packer.size()


class StructHandler:

    def __init__(self, static_value):
        self.struct_cls = static_value.type
        self.size_packer = get_handler(TypeFlag(int))

    def pack(self, struct):
        bytes_string = struct.to_bytes()
        return self.size_packer.pack(len(bytes_string)) + bytes_string

    def unpack_from(self, bytes_string):
        struct = self.struct_cls()
        self.unpack_merge(struct, bytes_string)
        return struct

    def unpack_merge(self, struct, bytes_string):
        struct.read_bytes(bytes_string[self.size_packer.size():])

    def size(self, bytes_string):
        return self.size_packer.unpack_from(bytes_string) + self.size_packer.size()


class FixedBitFieldHandler:
    """Bitfield packer for a TypeFlag which indicates the number of fields"""

    def __init__(self, size):
        self._size = size
        self._packer = handler_from_bit_length(size)
        self._packed_size = self._packer.size()

    def pack(self, field):
        # Get the smallest needed packer for this bitfield
        return self._packer.pack(field._value)

    def unpack_from(self, bytes_string):
        data = self._packer.unpack_from(bytes_string)
        field = BitField(self._size, data)
        return field

    def unpack_merge(self, field, bytes_string):
        field._value = self._packer.unpack_from(bytes_string)

    def size(self, bytes_string):
        return self._packed_size


class VariableBitFieldHandler:
    """Bitfield packer for a TypeFlag which does not indicate the number of
    fields"""

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
    def unpack_from(cls, bytes_string):
        field_size = cls.size_packer.unpack_from(bytes_string)

        if field_size:
            field_packer = handler_from_bit_length(field_size)
            data = field_packer.unpack_from(bytes_string[cls.size_packer.size():])

        else:
            data = 0

        field = BitField(field_size, data)
        return field

    @classmethod
    def unpack_merge(cls, field, bytes_string):
        field_size = cls.size_packer.unpack_from(bytes_string)
        if field_size:
            field_packer = handler_from_bit_length(field_size)
            field._value = field_packer.unpack_from(bytes_string[
                                                   cls.size_packer.size():])

        footprint = field.footprint
        if footprint:
            field_packer = handler_from_byte_length(footprint)
            field._value = field_packer.unpack_from(
                                bytes_string[cls.size_packer.size():])

    @classmethod
    def size(cls, bytes_string):
        field_size = cls.size_packer.unpack_from(bytes_string)
        field_handler = handler_from_bit_length(field_size)
        return field_handler.size() + cls.size_packer.size()


def bitfield_selector(flag):
    if not "fields" in flag.data:
        return VariableBitFieldHandler

    return FixedBitFieldHandler(flag.data['fields'])

# Define this before Struct
register_handler(BitField, bitfield_selector, True)

# Handle circular dependancy
from .network_struct import Struct
register_handler(Struct, StructHandler, True)

register_handler(Roles, RolesHandler)
register_handler(list, ListHandler, True)
register_handler(set, SetHandler, True)

ReplicableHandler = ReplicableBaseHandler()
register_handler(Replicable, ReplicableHandler)
register_handler(type(Replicable), ReplicableTypeHandler)

register_description(type(Replicable), type_description)
register_description(list, iterable_description)
register_description(set, iterable_description)
