from .bitfield import BitField
from .descriptors import TypeFlag
from .enums import IterableCompressionType, Roles
from .handler_interfaces import *
from .iterators import partition_iterable
from .logger import logger
from .replicable import Replicable
from .run_length_encoding import RunLengthCodec
from .serialiser import *
from .world_info import WorldInfo

from inspect import signature

__all__ = ['ReplicableTypeHandler', 'RolesHandler', 'ReplicableBaseHandler', 'StructHandler', 'BitFieldHandler',
           'class_type_description', 'iterable_description', 'is_variable_sized']


def class_type_description(cls):
    return hash(cls.type_name)


def iterable_description(iterable):
    return hash(tuple(iterable))


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
    def unpack_from(cls, bytes_string):
        name, name_length = cls.string_packer.unpack_from(bytes_string)
        return Replicable.from_type_name(name), name_length

    @classmethod
    def size(cls, bytes_string):
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
        local_role, local_size = packer.unpack_from(bytes_string)
        remote_role, remote_size = packer.unpack_from(bytes_string[local_size:])
        return Roles(local_role, remote_role), remote_size + local_size

    @classmethod
    def size(cls, bytes_string=None):
        return 2 * cls.packer.size()


class IterableHandler:

    iterable_cls = None
    iterable_add = None
    iterable_update = None
    unique_members = False

    def __init__(self, static_value):
        try:
            element_flag = static_value.data['element_flag']

        except KeyError as err:
            raise TypeError("Unable to pack iterable without full type information") from err

        int_flag = TypeFlag(int)
        variable_bitfield_flag = TypeFlag(BitField)

        self.element_type = element_flag.type
        self.element_packer = get_handler(element_flag)
        self.count_packer = get_handler(int_flag)
        self.bitfield_packer = get_handler(variable_bitfield_flag)

        self.is_variable_sized = is_variable_sized(self.element_packer)

        compression_type = static_value.data.get("compression", IterableCompressionType.no_compress)
        supports_rle = not self.__class__.unique_members

        # Select best compression method
        if compression_type == IterableCompressionType.auto:
            self.pack = self.auto_pack
            self.unpack_from = self.auto_unpack_from
            self.size = self.auto_size

        elif compression_type == IterableCompressionType.compress and supports_rle:
            self.pack = self.compressed_pack
            self.unpack_from = self.compressed_unpack_from
            self.size = self.compressed_size

        else:
            self.pack = self.uncompressed_pack
            self.unpack_from = self.uncompressed_unpack_from
            self.size = self.uncompressed_size

    def auto_pack(self, iterable):
        """Use smallest packing method to pack iterable in order to reduce data size

        :param iterable: iterable to pack
        """
        pack_type = self.count_packer.pack
        rle_encoded = self.compressed_pack(iterable)

        normal_encoded = self.uncompressed_pack(iterable)

        if len(rle_encoded) < len(normal_encoded):
            compression_type = IterableCompressionType.compress
            data =  pack_type(compression_type) + rle_encoded

        # If they are equal, non rle is faster to rebuild
        else:
            compression_type = IterableCompressionType.no_compress
            data = pack_type(compression_type) + normal_encoded

        return data

    def auto_unpack_from(self, bytes_string):
        """Unpack automatically compressed iterable

        :param bytes_string: incoming bytes offset to packed_iterable start
        """
        compression_type, type_size = self.count_packer.unpack_from(bytes_string)
        data = bytes_string[type_size:]

        if compression_type == IterableCompressionType.compress:
            result = self.compressed_unpack_from(data)

        else:
            result = self.uncompressed_unpack_from(data)

        return result[0], result[1] + type_size

    def auto_size(self, bytes_string):
        """Determine size of a variable compression iterable

        :param bytes_string: incoming bytes offset to packed_iterable start
        """
        pack_type, pack_size = self.count_packer.unpack_from(bytes_string)
        data = bytes_string[pack_size:]

        if pack_type == IterableCompressionType.compress:
            size = self.compressed_size(data)

        elif pack_type == IterableCompressionType.no_compress:
            size = self.uncompressed_size(data)

        else:
            raise TypeError("Invalid compression type used, or data is corrupt")

        return size + pack_size

    def compressed_pack(self, iterable):
        """Use RLE compression and bitfields (for booleans) to reduce data size

        :param iterable: iterable to pack
        """
        encoded_pairs = RunLengthCodec.encode(iterable)
        total_items = len(encoded_pairs)

        pack_length = self.count_packer.pack
        pack_key = self.element_packer.pack

        # Unfortunate special boolean case
        if self.element_type != bool:
            data = []
            append = data.append

            for length, key in encoded_pairs:
                append(pack_length(length))
                append(pack_key(key))

        else:
            if encoded_pairs:
                lengths, keys = zip(*encoded_pairs)
                data = [pack_length(length) for length in lengths]
                bitfield = BitField.from_iterable(keys)
                data.insert(0, self.bitfield_packer.pack(bitfield))
            else:
                data = []

        return pack_length(total_items) + b''.join(data)

    def compressed_unpack_from(self, bytes_string):
        """Unpack compressed iterable

        :param bytes_string: incoming bytes offset to packed_iterable start
        """
        count_unpacker = self.count_packer.unpack_from

        elements_count, count_size = count_unpacker(bytes_string)
        data = bytes_string[count_size:]

        element_unpack = self.element_packer.unpack_from

        add_element = self.__class__.iterable_add
        elements = self.iterable_cls()
        total_size = count_size

        if self.element_type == bool:
            if elements_count:
                bitfield, bitfield_size = self.bitfield_packer.unpack_from(data)
                data = data[bitfield_size:]

                for i in range(elements_count):
                    repeat, repeat_size = count_unpacker(data)
                    data = data[repeat_size:]

                    element = bitfield[i]

                    for _ in range(repeat):
                        add_element(elements, element)

                # Count size is the same as repeat size
                total_size += bitfield_size + count_size * elements_count

        # Faster unpacking
        else:
            for i in range(elements_count):
                repeat, repeat_size = count_unpacker(data)
                data = data[repeat_size:]

                element, element_size = element_unpack(data)
                data = data[element_size:]

                for _ in range(repeat):
                    add_element(elements, element)

                total_size += element_size + count_size

        return elements, total_size

    def compressed_size(self, bytes_string):
        """Determine size of a compressed iterable

        :param bytes_string: incoming bytes offset to packed_iterable start
        """
        elements_count, count_size = self.count_packer.unpack_from(bytes_string)
        data = bytes_string[count_size:]

        element_get_size = self.element_packer.size
        total_size = count_size

        # Faster unpacking
        if self.element_type == bool:
            if elements_count:
                bitfield_size = self.bitfield_packer.size(data)
                total_size += bitfield_size + count_size * elements_count

        elif not self.is_variable_sized:
            total_size += (element_get_size(None) + count_size) * elements_count

        else:
            for i in range(elements_count):
                element_data = data[count_size:]
                element_size = element_get_size(element_data)
                data = element_data[element_size:]

                total_size += element_size + count_size

        return total_size

    def uncompressed_pack(self, iterable):
        """Use simple header based count to pack iterable elements

        :param iterable: iterable to pack
        """
        element_pack = self.element_packer.pack
        element_count = self.count_packer.pack(len(iterable))
        packed_elements = b''.join([element_pack(x) for x in iterable])

        return element_count + packed_elements

    def uncompressed_unpack_from(self, bytes_string):
        """Use simple header based count to unpack iterable elements

        :param bytes_string: incoming bytes offset to packed_iterable start
        """
        element_count, count_size = self.count_packer.unpack_from(bytes_string)
        data = bytes_string[count_size:]
        element_get_size = self.element_packer.size
        element_unpack = self.element_packer.unpack_from

        # Fixed length unpacking
        if not self.is_variable_sized:
            element_size = element_get_size()
            partitioned_iterable = partition_iterable(data, element_size, element_count)
            elements = self.iterable_cls([element_unpack(x)[0] for x in partitioned_iterable])
            return elements, count_size + element_count * element_size

        # Variable length unpacking
        add_element = self.__class__.iterable_add
        elements = self.iterable_cls()
        total_size = count_size

        for _ in range(element_count):
            element, element_size = element_unpack(data)
            add_element(elements, element)

            data = data[element_size:]
            total_size += element_size

        return elements, total_size

    def unpack_merge(self, iterable, bytes_string):
        """Merge unpacked iterable data with existing iterable object

        :param iterable: iterable to merge with
        :param bytes_string: incoming bytes offset to packed_iterable start
        """
        elements, elements_size = self.unpack_from(bytes_string)
        self.__class__.iterable_update(iterable, elements)
        return elements_size

    def uncompressed_size(self, bytes_string):
        """Determine size of a packed (uncompressed) iterable

        :param bytes_string: incoming bytes offset to packed_iterable start
        """
        number_elements, elements_size = self.count_packer.unpack_from(bytes_string)
        data = bytes_string[elements_size:]
        element_get_size = self.element_packer.size

        if not self.is_variable_sized:
            return (number_elements * element_get_size()) + elements_size

        # Account for variable sized elements
        for i in range(number_elements):
            shift = element_get_size(data)
            elements_size += shift
            data = data[shift:]

        return elements_size


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
    unique_members = True

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
        instance_id, id_size = self.unpack_id(bytes_string)

        # Return only a replicable that was created by the network
        try:
            replicable = WorldInfo.get_replicable(instance_id)
            return replicable, id_size

        except LookupError:
            logger.exception("ReplicableBaseHandler: Couldn't find replicable with ID '{}'".format(instance_id))
            return None, id_size

    def size(self, bytes_string=None):
        return self._packer.size()


class StructHandler:

    def __init__(self, static_value):
        self.struct_cls = static_value.type

        if self.struct_cls is Struct:
            print("Warning: A Handler has been requested for a Struct type, cannot populate deserialised members")
        self.size_packer = get_handler(TypeFlag(int, max_value=1000))

    def pack(self, struct):
        bytes_string = struct.to_bytes()
        return self.size_packer.pack(len(bytes_string)) + bytes_string

    def unpack_from(self, bytes_string):
        struct = self.struct_cls()
        struct_size = self.unpack_merge(struct, bytes_string)
        return struct, struct_size

    def unpack_merge(self, struct, bytes_string):
        struct_size, length_size = self.size_packer.unpack_from(bytes_string)
        struct.read_bytes(bytes_string[length_size:])
        return length_size + struct_size

    def size(self, bytes_string):
        struct_size, length_size = self.size_packer.unpack_from(bytes_string)
        return struct_size + length_size


class BitFieldHandler:
    """Bitfield packer for a TypeFlag which indicates the number of fields"""

    def __init__(self, type_flag):
        fields = type_flag.data.get("fields")

        if fields is None:
            self.pack = self.variable_pack
            self.unpack_from = self.variable_unpack_from
            self.unpack_merge = self.variable_unpack_merge
            self.size = self.variable_size
            self._packer = handler_from_byte_length(1)

        else:
            self.pack = self.fixed_pack
            self.unpack_from = self.fixed_unpack_from
            self.unpack_merge = self.fixed_unpack_merge
            self.size = self.fixed_size
            self._size = fields
            self._packer = handler_from_bit_length(fields)
            self._packed_size = BitField.calculate_footprint(fields)

    def fixed_pack(self, field):
        # Get the smallest needed packer for this bitfield
        return field.to_bytes()

    def fixed_unpack_from(self, bytes_string):
        return BitField.from_bytes(self._size, bytes_string)

    def fixed_unpack_merge(self, field, bytes_string):
        field[:], field_size = self.fixed_unpack_from(bytes_string)
        return field_size

    def fixed_size(self, bytes_string=None):
        return self._packed_size

    def variable_pack(self, field):
        packed_size = self._packer.pack(len(field))

        # Only pack data if we can
        if len(field):
            return packed_size + field.to_bytes()

        else:
            return packed_size

    def variable_unpack_from(self, bytes_string):
        field_bits, packer_size = self._packer.unpack_from(bytes_string)
        if field_bits:
            field, field_size_bytes = BitField.from_bytes(field_bits, bytes_string[packer_size:])
        else:
            field = BitField(field_bits)
        return field, field_size_bytes + packer_size

    def variable_unpack_merge(self, field, bytes_string):
        field[:], packer_size = self.variable_unpack_from(bytes_string)
        return packer_size

    def variable_size(self, bytes_string):
        field_size, packed_size = self._packer.unpack_from(bytes_string)
        return BitField.calculate_footprint(field_size) + packed_size


# Define this before Struct
register_handler(BitField, BitFieldHandler, True)

# Handle circular dependancy
from .network_struct import Struct
register_handler(Struct, StructHandler, True)

register_handler(Roles, RolesHandler)
register_handler(list, ListHandler, True)
register_handler(set, SetHandler, True)

ReplicableHandler = ReplicableBaseHandler()
register_handler(Replicable, ReplicableHandler)
register_handler(type(Replicable), ReplicableTypeHandler)

register_description(type(Replicable), class_type_description)
register_description(list, iterable_description)
register_description(set, iterable_description)
