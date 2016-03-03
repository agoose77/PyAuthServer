from math import ceil
from struct import Struct, pack, unpack_from

from ..type_serialisers import register_serialiser


__all__ = ['bits_to_bytes', 'next_or_equal_power_of_two']


def execute_and_return_pair(function_string, locals_dict):
    """Create function from definition string.

    :param locals_dict: locals dictionary
    """
    original_locals = locals_dict.copy()
    exec(function_string, globals(), original_locals)

    # Find the added function
    for name, value in original_locals.items():
        if locals_dict.get(name) != value:
            new_key = name
            break

    else:
        raise RuntimeError("Couldn't find defined function. This shouldn't happen")

    return new_key, original_locals[new_key]


def build_struct_serialiser(name, character_format, order_format="!"):
    """Create handler for data with struct formatting

    :param name: name of handler class
    :param character_format: format string of handler
    :param order_format: format string of byte order
    """
    struct_obj = Struct(order_format + character_format)
    format_size = struct_obj.size

    methods = ("""def unpack_from(bytes_string, offset=0, unpacker=struct_obj.unpack_from):\n\t
               return unpacker(bytes_string, offset)[0], {format_size}""",
               """def size(bytes_string=None):\n\treturn {format_size}""",
               """def pack_multiple(value, count, pack=pack, character_format=character_format):\n\t"""
               """return pack('{order_format}' + '{character_format}' * count, *value)""",
               """def unpack_multiple(bytes_string, count, offset=0, unpack_from=unpack_from):\n\t"""
               """data = unpack_from('{order_format}' + '{character_format}' * count, bytes_string, offset)\n\t"""
               """return data, {format_size} * count""",
               """pack=struct_obj.pack""")

    cls_dict = {"supports_mutable_unpacking": False}

    locals_ = locals()
    for method_string in methods:
        formatted_string = method_string.format(**locals_)
        value_name, value = execute_and_return_pair(formatted_string, locals_)

        cls_dict[value_name] = value

    return type(name, (), cls_dict)


UInt32 = build_struct_serialiser("UInt32", "I")
UInt16 = build_struct_serialiser("UInt16", "H")
UInt64 = build_struct_serialiser("UInt64", "Q")
UInt8 = build_struct_serialiser("UInt8", "B")
Int32 = build_struct_serialiser("UInt32", "i")
Int16 = build_struct_serialiser("UInt16", "h")
Int64 = build_struct_serialiser("UInt64", "q")
Int8 = build_struct_serialiser("UInt8", "b")
Float32 = build_struct_serialiser("Float32", "f")
Float64 = build_struct_serialiser("Float64", "d")


int_serialisers = [UInt8, UInt16, UInt32, UInt64]
size_to_int_serialiser = {packer.size(): packer for packer in int_serialisers}


def bits_to_bytes(bits):
    """Determines how many bytes are required to pack a number of bits

    :param bits: number of bits required
    """
    return ceil(bits / 8)


def next_or_equal_power_of_two(value):
    """Return next power of 2 greater than or equal to value"""
    if value > 0:
        value -= 1

    shift = 1

    while (value + 1) & value:
        value |= value >> shift
        shift *= 2

    return value + 1


def _serialiser_from_bit_length(total_bits):
    """Return the correct integer handler for a given number of bits

    :param total_bits: total number of bits required
    """
    total_bytes = bits_to_bytes(total_bits)
    return _serialiser_from_byte_length(total_bytes)


def _serialiser_from_byte_length(total_bytes):
    """Return the smallest handler needed to pack a number of bytes

    :param total_bytes: number of bytes needed to pack
    :rtype: :py:class:`network.serialiser.IDataSerialiser`
    """
    rounded_bytes = next_or_equal_power_of_two(total_bytes)

    try:
        return size_to_int_serialiser[rounded_bytes]

    except KeyError as err:
        raise ValueError("Integer too large to pack: {} bytes".format(total_bytes)) from err

    return packer


def _serialiser_from_int(value):
    """Return the smallest integer packer capable of packing a given integer

    :param value: integer value
    """
    return _serialiser_from_bit_length(value.bit_length())


class BoolSerialiser(UInt8):
    """Serialiser for boolean type"""

    @classmethod
    def unpack_from(self, bytes_string, offset=0, unpack_from=UInt8.unpack_from):
        value, size = unpack_from(bytes_string, offset)
        return bool(value), size

    @classmethod
    def unpack_multiple(self, bytes_string, count, offset=0, unpack_multiple=UInt8.unpack_multiple):
        value, size = self.unpack_multiple(bytes_string, count, offset)
        return [bool(x) for x in value], size


class _BytesSerialiser:

    classes = {}

    def __new__(cls, flag, logger):
        header_max_value = flag.data.get("max_length", 255)

        try:
            new_cls = cls.classes[header_max_value]

        except KeyError:
            packer = _serialiser_from_int(header_max_value)

            methods = ("""def unpack_from(bytes_string, offset=0, *, unpacker=packer.unpack_from):\n\t"""
               """length, length_size = unpacker(bytes_string, offset)\n\t"""
               """end_index = length + length_size\n\t"""
               """value = bytes_string[length_size + offset: end_index + offset]\n\t"""
               """return value, end_index""",
               """def pack_multiple(value, count, pack_lengths=packer.pack_multiple):\n\t"""
               """lengths = [len(x) for x in value]\n\tpacked_lengths = pack_lengths(lengths, len(lengths))\n\t"""
               """return packed_lengths + b''.join(value)""",
               """def unpack_multiple(bytes_string, count, offset=0, unpack_lengths=packer.unpack_multiple):"""
               """\n\t_offset=offset\n\tlengths, length_offset=unpack_lengths(bytes_string, """
               """count, offset)\n\toffset += length_offset\n\tdata = []\n\tfor length in lengths:\n\t\t"""
               """data.append(bytes_string[offset: offset+length])\n\t\toffset += length\n\t"""
               """return data, offset - _offset""",
               """def size(bytes_string, unpacker=packer.unpack_from):\n\t"""
               """length, length_size = unpacker(bytes_string)\n\treturn length + length_size""",
               """def pack(bytes_string, packer=packer.pack):\n\treturn packer(len(bytes_string)) + bytes_string""")

            cls_dict = {"supports_mutable_unpacking": False}
            locals_ = locals()
            for method_string in methods:
                value_name, value = execute_and_return_pair(method_string, locals_)

                cls_dict[value_name] = value

            new_cls = type("BytesSerialiser", (), cls_dict)

            cls.classes[header_max_value] = new_cls

        return new_cls


class _StringSerialiser:

    classes = {}

    def __new__(cls, flag, logger):
        header_max_value = flag.data.get("max_length", 255)

        try:
            new_cls = cls.classes[header_max_value]

        except KeyError:
            packer = _serialiser_from_int(header_max_value)

            methods = ("""def unpack_from(bytes_string, offset=0, *, unpacker=packer.unpack_from):
                length, length_size = unpacker(bytes_string, offset)\n\t
                end_index = length + length_size\n\t
                value = bytes_string[length_size + offset: end_index + offset]\n\t
                return value.decode(), end_index""",
                """def pack(string_, packer=packer.pack):\n\treturn packer(len(string_)) + string_.encode()""",
                """def pack_multiple(value, count, pack_lengths=packer.pack_multiple):\n\t"""
                """lengths = [len(x) for x in value]\n\tpacked_lengths = pack_lengths(lengths, len(lengths))\n\t"""
                """return packed_lengths + ''.join(value).encode()""",
                """def unpack_multiple(bytes_string, count, offset=0, unpack_lengths=packer.unpack_multiple):"""
                """\n\t_offset=offset\n\tlengths, length_offset=unpack_lengths(bytes_string, count, offset)\n\t"""
                """offset += length_offset\n\tdata = []\n\tfor length in lengths:\n\t\t"""
                """data.append(bytes_string[offset: offset+length].decode())\n\t\toffset += length\n\t"""
                """return data, offset - _offset""",)

            cls_dict = {"supports_mutable_unpacking": False}
            locals_ = locals()
            for method_string in methods:
                value_name, value = execute_and_return_pair(method_string, locals_)

                cls_dict[value_name] = value

            new_cls = type("StringSerialiser", (), cls_dict)
            cls.classes[header_max_value] = new_cls

        return new_cls


def _float_serialiser(flag, logger):
    """Return  the correct float handler using meta information from a given type_flag"""
    return Float64 if flag.data.get("max_precision") else Float32


def _int_serialiser(flag, logger):
    """Return the correct int handler using meta information from a given type_flag"""
    if "max_value" in flag.data:
        new_cls = _serialiser_from_int(flag.data["max_value"])

    else:
        new_cls = _serialiser_from_bit_length(flag.data.get('max_bits', 8))

    return new_cls


def _bool_serialiser(flag, logger):
    return BoolSerialiser


# Register handlers for native types
register_serialiser(str, _StringSerialiser)
register_serialiser(bytes, _BytesSerialiser)
register_serialiser(int, _int_serialiser)
register_serialiser(bool, _bool_serialiser)
register_serialiser(float, _float_serialiser)
