from .bitfield import BitField
from .descriptors import TypeFlag
from .enums import IterableCompressionType, Roles
from .handler_interfaces import *
from .iterators import partition_iterable
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

        assert len(data) == self.auto_size(data)
        return data

    def auto_unpack_from(self, bytes_string):
        """Unpack automatically compressed iterable

        :param bytes_string: incoming bytes offset to packed_iterable start
        """
        get_type = self.count_packer.unpack_from
        type_size = self.count_packer.size()

        pack_type = get_type(bytes_string)
        data = bytes_string[type_size:]

        if pack_type == IterableCompressionType.compress:
            return self.compressed_unpack_from(data)

        else:
            return self.uncompressed_unpack_from(data)

    def auto_size(self, bytes_string):
        """Determine size of a variable compression iterable

        :param bytes_string: incoming bytes offset to packed_iterable start
        """
        get_type = self.count_packer.unpack_from
        count_size = self.count_packer.size()

        pack_type = get_type(bytes_string)
        data = bytes_string[count_size:]

        if pack_type == IterableCompressionType.compress:
            size = self.compressed_size(data)

        elif pack_type == IterableCompressionType.no_compress:
            size = self.uncompressed_size(data)

        else:
            raise TypeError()

        return size + count_size

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

        bytes_string = b''.join(data)
        elements_count = pack_length(total_items)

        data = elements_count + bytes_string

        assert len(data) == self.compressed_size(data)
        return data

    def compressed_unpack_from(self, bytes_string):
        """Unpack compressed iterable

        :param bytes_string: incoming bytes offset to packed_iterable start
        """
        get_count = self.count_packer.unpack_from
        count_size = self.count_packer.size()

        elements_count = get_count(bytes_string)
        data = bytes_string[count_size:]

        element_get_size = self.element_packer.size
        element_unpack = self.element_packer.unpack_from

        elements = self.iterable_cls()
        add = self.__class__.iterable_add

        if self.element_type == bool:
            if elements_count:
                bitfield = self.bitfield_packer.unpack_from(data)
                data = data[self.bitfield_packer.size(data):]

                for i in range(elements_count):
                    repeat = get_count(data)
                    data = data[count_size:]

                    element = bitfield[i]

                    for i in range(repeat):
                        add(elements, element)

        # Faster unpacking
        elif not self.is_variable_sized:
            element_size = element_get_size(None)
            for i in range(elements_count):
                repeat = get_count(data)
                element_data = data[count_size:]

                element = element_unpack(element_data)

                # May be worth just removing this
                data = element_data[element_size:]

                for i in range(repeat):
                    add(elements, element)

        else:
            for i in range(elements_count):
                repeat = get_count(data)
                element_data = data[count_size:]

                element = element_unpack(element_data)

                # May be worth just removing this
                data = element_data[element_get_size(element_data):]

                for i in range(repeat):
                    add(elements, element)

        return elements

    def compressed_size(self, bytes_string):
        """Determine size of a compressed iterable

        :param bytes_string: incoming bytes offset to packed_iterable start
        """
        get_count = self.count_packer.unpack_from
        count_size = self.count_packer.size()

        elements_count = get_count(bytes_string)
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
        data = element_count + packed_elements


        assert len(data) == self.uncompressed_size(data)
        return data

    def uncompressed_unpack_from(self, bytes_string):
        """Use simple header based count to unpack iterable elements

        :param bytes_string: incoming bytes offset to packed_iterable start
        """
        size = self.count_packer.unpack_from(bytes_string)
        data = bytes_string[self.count_packer.size():]
        element_get_size = self.element_packer.size
        element_unpack = self.element_packer.unpack_from

        # Fixed length unpacking
        if not self.is_variable_sized:
            element_size = element_get_size()
            partitioned_iterable = partition_iterable(data, element_size, size)
            return self.iterable_cls([element_unpack(x) for x in partitioned_iterable])

        # Variable length unpacking
        elements = self.iterable_cls()
        add = self.__class__.iterable_add

        for _ in range(size):
            shift = element_get_size(data)
            add(elements, element_unpack(data))
            data = data[shift:]

        return elements

    def unpack_merge(self, iterable, bytes_string):
        """Merge unpacked iterable data with existing iterable object

        :param iterable: iterable to merge with
        :param bytes_string: incoming bytes offset to packed_iterable start
        """
        self.__class__.iterable_update(iterable, self.unpack_from(bytes_string))

    def uncompressed_size(self, bytes_string):
        """Determine size of a packed (uncompressed) iterable

        :param bytes_string: incoming bytes offset to packed_iterable start
        """
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
        instance_id = self.unpack_id(bytes_string)

        # Return only a replicable that was created by the network

        try:
            replicable = WorldInfo.get_replicable(instance_id)
            return replicable

        except (LookupError):
            print("ReplicableBaseHandler: Couldn't find replicable with ID '{}'".format(instance_id))
            return

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
        self.unpack_merge(struct, bytes_string)
        return struct

    def unpack_merge(self, struct, bytes_string):
        struct.read_bytes(bytes_string[self.size_packer.size():])

    def size(self, bytes_string):
        return self.size_packer.unpack_from(bytes_string) + self.size_packer.size()


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
            self._packed_size = self._packer.size()

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
        data = bytes_string[:self._packed_size]
        field = BitField.from_bytes(self._size, data)
        return field

    def fixed_unpack_merge(self, field, bytes_string):
        field[:] = self.fixed_unpack_from(bytes_string)

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
        field_size = self._packer.unpack_from(bytes_string)
        if field_size:
            data = bytes_string[self._packer.size():]
            field = BitField.from_bytes(field_size, data)
            return field

        field = BitField(field_size)
        return field

    def variable_unpack_merge(self, field, bytes_string):
        field[:] = self.variable_unpack_from(bytes_string)

    def variable_size(self, bytes_string):
        field_size = self._packer.unpack_from(bytes_string)
        return BitField.calculate_footprint(field_size) + self._packed_size


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
