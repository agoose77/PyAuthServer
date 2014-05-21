from struct import Struct as PyStruct
from math import ceil

from .handler_interfaces import register_handler

__all__ = ['IStruct', 'UInt16', 'UInt32', 'UInt64', 'UInt8', 'Float32', 'Float64', 'bits_to_bytes',
           'handler_from_bit_length', 'handler_from_int', 'handler_from_byte_length', 'StringHandler',
           'BytesHandler', 'int_selector', 'next_or_equal_power_of_two', 'BoolHandler']


class IStruct(PyStruct):

    def size(self, bytes_string=None):
        return super().size

    @property
    def unpack(self):
        raise AttributeError("'unpack' attribute of IStruct instances should not be used. See unpack_from")

    def unpack_from(self, bytes_string):
        return super().unpack_from(bytes_string)[0], super().size

    def __str__(self):
        return "<{} Byte Handler>"


UInt32 = IStruct("!I")
UInt16 = IStruct("!H")
UInt64 = IStruct("!Q")
UInt8 = IStruct("!B")
Float32 = IStruct("!f")
Float64 = IStruct("!d")


int_packers = [UInt8, UInt16, UInt32, UInt64]
int_sized = {x.size(): x for x in int_packers}


def bits_to_bytes(bits):
    return ceil(bits / 8)


def next_or_equal_power_of_two(value):
    """Return next power of 2 greater than or equal to value

    :param value: value to round
    """
    if value > 0:
        value -= 1
    else:
        value = 1
    shift = 1
    while (value + 1) & value:
        value |= value >> shift
        shift *= 2
    return value + 1


def float_selector(type_flag):
    return Float64 if type_flag.data.get("max_precision") else Float32


def handler_from_bit_length(total_bits):
    total_bytes = bits_to_bytes(total_bits)
    return handler_from_byte_length(total_bytes)


def handler_from_byte_length(total_bytes):
    """Find the smallest handler needed to pack a number of bytes

    :param total_bytes: number of bytes needed to pack
    :rtype: :py:class:`network.serialiser.IStruct`"""
    rounded_bytes = next_or_equal_power_of_two(total_bytes)

    try:
        return int_sized[rounded_bytes]

    except KeyError as err:
        raise ValueError("Integer too large to pack: {} bytes".format(total_bytes)) from err

    return packer


def handler_from_int(value):
    return handler_from_bit_length(value.bit_length())


def int_selector(type_flag):
    if "max_value" in type_flag.data:
        return handler_from_int(type_flag.data["max_value"])

    return handler_from_bit_length(type_flag.data.get('max_bits', 8))


class BoolHandler:
    unpacker = UInt8.unpack_from

    @classmethod
    def unpack_from(cls, bytes_string):
        value, size = cls.unpacker(bytes_string)
        return bool(value), size

    size = UInt8.size
    pack = UInt8.pack


class BytesHandler:

    def __init__(self, type_flag):
        header_max_value = type_flag.data.get("max_length", 255)
        self.packer = handler_from_int(header_max_value)

    def pack(self, bytes_string):
        return self.packer.pack(len(bytes_string)) + bytes_string

    def size(self, bytes_string):
        length, length_size = self.packer.unpack_from(bytes_string)
        return length + length_size

    def unpack_from(self, bytes_string):
        length, length_size = self.packer.unpack_from(bytes_string)

        end_index = length + length_size
        value = bytes_string[length_size: end_index]

        return value, end_index


class StringHandler(BytesHandler):

    def pack(self, str_):
        return super().pack(str_.encode())

    def unpack_from(self, bytes_string):
        encoded_string, size = super().unpack_from(bytes_string)

        return bytes(encoded_string).decode(), size

if True:
    # Register handlers for native types
    register_handler(bool, BoolHandler)
    register_handler(str, StringHandler, is_callable=True)
    register_handler(bytes, BytesHandler, is_callable=True)
    register_handler(int, int_selector, is_callable=True)
    register_handler(float, float_selector, is_callable=True)
