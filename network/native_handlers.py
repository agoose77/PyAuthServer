from .bitfield import BitField
from .type_flag import TypeFlag
from .enums import IterableCompressionType, Roles
from .handlers import *
from .iterators import partition_iterable
from .logger import logger
from .replicable import Replicable
from .run_length_encoding import RunLengthCodec
from .serialiser import *
from .world_info import WorldInfo

from inspect import signature
from itertools import chain


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
    def pack_multiple(cls, values, count):
        names = [c.type_name for c in values]
        return cls.string_packer.pack_multiple(names, count)

    @classmethod
    def unpack_from(cls, bytes_string, offset=0):
        name, name_length = cls.string_packer.unpack_from(bytes_string, offset)
        return Replicable.from_type_name(name), name_length

    @classmethod
    def unpack_multiple(cls, bytes_string, count, offset=0):
        names, names_length = cls.string_packer.unpack_multiple(bytes_string, count, offset)
        get_class = Replicable.from_type_name
        return [get_class(n) for n in names], names_length

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
    def pack_multiple(cls, roles, count):
        pack = cls.packer.pack
        packed_roles = [(pack(roles_.remote), pack(roles_.local)) for roles_ in roles]
        return b''.join(chain.from_iterable(packed_roles))

    @classmethod
    def unpack_from(cls, bytes_string, offset=0):
        packer = cls.packer
        local_role, local_size = packer.unpack_from(bytes_string, offset)
        remote_role, remote_size = packer.unpack_from(bytes_string, offset + local_size)
        return Roles(local_role, remote_role), remote_size + local_size

    @classmethod
    def unpack_multiple(cls, bytes_string, count, offset=0):
        role_values, size = cls.packer.unpack_multiple(bytes_string, count, offset)
        roles = [Roles(role_values[i], role_values[(i + 1)]) for i in range(count)]
        return roles, size

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

        compression_type = static_value.data.get("compression", IterableCompressionType.auto)
        supports_compression = not self.__class__.unique_members

        # Select best compression method
        if not supports_compression:
            compression_type = IterableCompressionType.no_compress

        if compression_type == IterableCompressionType.auto:
            self.pack = self.auto_pack
            self.unpack_from = self.auto_unpack_from
            self.size = self.auto_size

        elif compression_type == IterableCompressionType.compress:
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
            data = pack_type(compression_type) + rle_encoded

        # If they are equal, non rle is faster to rebuild
        else:
            compression_type = IterableCompressionType.no_compress
            data = pack_type(compression_type) + normal_encoded

        return data

    def auto_unpack_from(self, bytes_string, offset=0):
        """Unpack automatically compressed iterable

        :param bytes_string: incoming bytes offset to packed_iterable start
        """
        compression_type, type_size = self.count_packer.unpack_from(bytes_string, offset)

        if compression_type == IterableCompressionType.compress:
            iterable, size = self.compressed_unpack_from(bytes_string, offset + type_size)

        else:
            iterable, size = self.uncompressed_unpack_from(bytes_string, offset + type_size)

        return iterable, size + type_size

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
            # Encode all lengths first then elements
            packed = [(pack_length(length), pack_key(key)) for length, key in encoded_pairs]
            data = [x for y in zip(*packed) for x in y]

        else:
            if encoded_pairs:
                lengths, keys = zip(*encoded_pairs)
                data = [pack_length(length) for length in lengths]

                bitfield = BitField.from_iterable(keys)
                data.insert(0, self.bitfield_packer.pack(bitfield))

            else:
                data = []

        return pack_length(total_items) + b''.join(data)

    def compressed_unpack_from(self, bytes_string, offset=0):
        """Unpack compressed iterable

        :param bytes_string: incoming bytes offset to packed_iterable start
        """
        count_unpacker = self.count_packer.unpack_from
        elements_count, count_size = count_unpacker(bytes_string, offset)
        element_unpack = self.element_packer.unpack_from
        count_multiple_unpacker = self.count_packer.unpack_multiple

        original_offset = offset
        offset += count_size

        element_list = []
        extend_elements = element_list.extend

        if self.element_type is bool:
            if elements_count:
                bitfield, bitfield_size = self.bitfield_packer.unpack_from(bytes_string, offset)
                offset += bitfield_size

                element_counts, _offset = count_multiple_unpacker(bytes_string, elements_count, offset)
                offset += _offset

                elements = bitfield[:element_counts]
                for repeat, element in zip(element_counts, elements):
                    extend_elements([element] * repeat)

        else:
            element_counts, _offset = count_multiple_unpacker(bytes_string, elements_count, offset)
            offset += _offset
            # Todo all packers multiples
            for repeat in element_counts:
                element, element_size = element_unpack(bytes_string, offset)
                offset += element_size

                extend_elements([element] * repeat)

        elements = self.iterable_cls(element_list)
        return elements, offset - original_offset

    def compressed_size(self, bytes_string):
        """Determine size of a compressed iterable

        :param bytes_string: incoming bytes offset to packed_iterable start
        """
        elements_count, count_size = self.count_packer.unpack_from(bytes_string)
        data = bytes_string[count_size:]

        element_get_size = self.element_packer.size
        total_size = count_size

        # Faster unpacking
        if self.element_type is bool:
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
        if self.element_type is bool:
            bitfield = BitField.from_iterable(iterable)
            return self.bitfield_packer.pack(bitfield)

        element_pack = self.element_packer.pack
        element_count = self.count_packer.pack(len(iterable))
        packed_elements = b''.join([element_pack(x) for x in iterable])

        return element_count + packed_elements

    def uncompressed_unpack_from(self, bytes_string, offset=0):
        """Use simple header based count to unpack iterable elements

        :param bytes_string: incoming bytes offset to packed_iterable start
        """
        if self.element_type is bool:
            bitfield, bitfield_size = self.bitfield_packer.unpack_from(bytes_string, offset)
            return self.iterable_cls(bitfield), bitfield_size

        element_count, count_size = self.count_packer.unpack_from(bytes_string, offset)

        element_get_size = self.element_packer.size
        element_unpack = self.element_packer.unpack_from

        original_offset = offset
        offset += count_size

        # Fixed length unpacking
        if not self.is_variable_sized:
            data = bytes_string[offset:]
            element_size = element_get_size()
            partitioned_iterable = partition_iterable(data, element_size, element_count)
            elements = self.iterable_cls([element_unpack(x)[0] for x in partitioned_iterable])
            return elements, count_size + element_count * element_size

        # Variable length unpacking
        add_element = self.__class__.iterable_add
        elements = self.iterable_cls()

        for _ in range(element_count):
            element, element_size = element_unpack(bytes_string, offset)
            add_element(elements, element)

            offset += element_size

        return elements, offset - original_offset

    def unpack_merge(self, iterable, bytes_string, offset=0):
        """Merge unpacked iterable data with existing iterable object

        :param iterable: iterable to merge with
        :param bytes_string: incoming bytes offset to packed_iterable start
        """
        elements, elements_size = self.unpack_from(bytes_string, offset)
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

    def iterable_update(list_, data):
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
    Packs replicable references and unpacks to reference
    """

    def __init__(self):
        id_flag = TypeFlag(int, max_value=Replicable._MAXIMUM_REPLICABLES)
        self._packer = get_handler(id_flag)

    def pack(self, replicable):
        """Pack replicable using its instance ID

        :param replicable: :py:code:`network.replicble.Replicable` instance
        """
        return self.pack_id(replicable.instance_id)

    def pack_id(self, id_):
        """Pack replicable instance ID

        :param id_: instance ID
        """
        return self._packer.pack(id_)

    def pack_multiple(self, replicables, count):
        instance_ids = [r.instance_id for r in replicables]
        return self._packer.pack_multiple(instance_ids, count)

    def unpack_id(self, bytes_string, offset=0):
        """Unpack replicable instance ID

        :param bytes_string: packed ID string
        """
        return self._packer.unpack_from(bytes_string, offset)

    def unpack_from(self, bytes_string, offset=0):
        """Unpack replicable instance ID

        :param bytes_string: packed ID string
        """
        instance_id, id_size = self.unpack_id(bytes_string, offset)

        # Return only a replicable that was created by the network
        try:
            replicable = WorldInfo.get_replicable(instance_id)
            return replicable, id_size

        except LookupError:
            logger.exception("ReplicableBaseHandler: Couldn't find replicable with ID '{}'".format(instance_id))
            return None, id_size

    def unpack_multiple(self, bytes_string, count, offset=0):
        instance_ids, offset = self._packer.unpack_multiple(bytes_string, count, offset)
        get_replicable = WorldInfo.get_replicable
        replicables = []
        for instance_id in instance_ids:
            try:
                replicable = get_replicable(instance_id)

            except LookupError:
                replicable = None
                logger.exception("ReplicableBaseHandler: Couldn't find replicable with ID '{}'".format(instance_id))

            replicables.append(replicable)

        return replicables, offset

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

    def pack_multiple(self, structs, count):
        struct_data = [struct.to_bytes() for struct in structs]
        lengths = [len(x) for x in struct_data]
        size_data = self.size_packer.pack_multiple(lengths, count)
        return b''.join(size_data + struct_data)

    def unpack_from(self, bytes_string, offset=0):
        struct = self.struct_cls()
        struct_size = self.unpack_merge(struct, bytes_string, offset)
        return struct, struct_size

    def unpack_merge(self, struct, bytes_string, offset=0):
        struct_size, length_size = self.size_packer.unpack_from(bytes_string, offset)
        struct.read_bytes(bytes_string, length_size + offset)
        return length_size + struct_size

    def unpack_multiple(self, bytes_string, count, offset=0):
        structs = []
        for _ in range(count):
            struct = self.struct_cls()
            structs.append(struct)
            struct_size, length_size = self.size_packer.unpack_from(bytes_string, offset)
            struct.read_bytes(bytes_string, length_size + offset)
            offset += length_size + struct_size

    def size(self, bytes_string):
        struct_size, length_size = self.size_packer.unpack_from(bytes_string)
        return struct_size + length_size


class BitFieldHandler:
    """Bitfield packer for a TypeFlag which indicates the number of fields"""

    def __init__(self, type_flag):
        fields = type_flag.data.get("fields")

        if fields is None:
            self.pack = self.variable_pack
            self.pack_multiple = self.variable_pack_multiple
            self.unpack_from = self.variable_unpack_from
            self.unpack_multiple = self.variable_unpack_multiple
            self.size = self.variable_size
            self._packer = handler_from_byte_length(1)

        else:
            self.pack = self.fixed_pack
            self.pack_multiple = self.fixed_pack_multiple
            self.unpack_from = self.fixed_unpack_from
            self.unpack_multiple = self.fixed_pack_multiple
            self.size = self.fixed_size
            self._size = fields
            self._packer = handler_from_bit_length(fields)
            self._packed_size = BitField.calculate_footprint(fields)

    def fixed_pack(self, field):
        # Get the smallest needed packer for this bitfield
        return field.to_bytes()

    def fixed_pack_multiple(self, fields, count):
        return b''.join([field.to_bytes() for field in fields])

    def fixed_unpack_from(self, bytes_string, offset=0):
        return BitField.from_bytes(self._size, bytes_string, offset)

    def fixed_unpack_multiple(self, bytes_string, count, offset=0):
        return [BitField.from_bytes(self._size, bytes_string, offset + i * self._size)
                for i in range(count)], count * self._size

    def fixed_size(self, bytes_string=None):
        return self._packed_size

    def variable_pack(self, field):
        packed_size = self._packer.pack(len(field))

        # Only pack data if we can
        if len(field):
            return packed_size + field.to_bytes()

        else:
            return packed_size

    def variable_pack_multiple(self, fields, count):
        lengths = [len(field) for field in fields]
        data = [field.to_bytes() for field in fields]
        return self._packer.pack_multiple(lengths, count) + b''.join(data)

    def variable_unpack_from(self, bytes_string, offset=0):
        field_bits, packer_size = self._packer.unpack_from(bytes_string, offset)
        offset += packer_size

        field, field_size_bytes = BitField.from_bytes(field_bits, bytes_string, offset)
        return field, field_size_bytes + packer_size

    def variable_unpack_multiple(self, bytes_string, count, offset=0):
        _offset = offset
        lengths, length_size = self._packer.unpack_multiple(bytes_string, count, offset)
        offset += length_size
        fields = []
        for length in lengths:
            field, field_size = BitField.from_bytes(length, bytes_string, offset)
            offset += field_size
            fields.append(field)

        return fields, offset - _offset

    def unpack_merge(self, field, bytes_string, offset=0):
        field[:], packer_size = self.unpack_from(bytes_string, offset)
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
