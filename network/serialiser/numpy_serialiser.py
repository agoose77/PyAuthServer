from math import ceil

from numpy import uint8, uint16, uint32, uint64, float32, float64, fromstring
from network.type_serialisers import register_serialiser


__all__ = ['NumpyStruct', 'UInt16', 'UInt32', 'UInt64', 'UInt8', 'Float32', 'Float64', 'bits_to_bytes',
           'handler_from_bit_length', 'handler_from_int', 'handler_from_byte_length', 'StringSerialiser',
           'BytesSerialiser', 'int_selector', 'next_or_equal_power_of_two', 'BoolSerialiser']


class NumpyStruct:

    def __init__(self, numpy_obj, size):
        self._numpy_obj = numpy_obj
        self._size = size

    def size(self, bytes_string=None):
        return self._size

    def unpack_from(self, bytes_string):
        size = self._size
        value = fromstring(bytes_string[:size], dtype=self._numpy_obj)[0]
        return value, size

    def pack(self, value):
        obj = self._numpy_obj(value)
        return obj.tostring()

    def __str__(self):
        return "<{} Byte Serialiser>"


UInt8 = NumpyStruct(uint8, 1)
UInt16 = NumpyStruct(uint16, 2)
UInt32 = NumpyStruct(uint32, 4)
UInt64 = NumpyStruct(uint64, 8)
Float32 = NumpyStruct(float32, 4)
Float64 = NumpyStruct(float64, 8)


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
    :rtype: :py:class:`network.serialiser.IDataSerialiser`"""
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


class BoolSerialiser:
    unpacker = UInt8.unpack_from

    @classmethod
    def unpack_from(cls, bytes_string):
        value, size = cls.unpacker(bytes_string)
        return bool(value), size

    size = UInt8.size
    pack = UInt8.pack


class BytesSerialiser:

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


class StringSerialiser(BytesSerialiser):

    def pack(self, str_):
        return super().pack(str_.encode())

    def unpack_from(self, bytes_string):
        encoded_string, size = super().unpack_from(bytes_string)

        return encoded_string.decode(), size


# Register handlers for native types
register_serialiser(bool, BoolSerialiser)
register_serialiser(str, StringSerialiser, is_callable=True)
register_serialiser(bytes, BytesSerialiser, is_callable=True)
register_serialiser(int, int_selector, is_callable=True)
register_serialiser(float, float_selector, is_callable=True)
