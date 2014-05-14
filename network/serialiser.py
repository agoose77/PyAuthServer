from struct import Struct as PyStruct
from math import ceil

from .handler_interfaces import register_handler

__all__ = ['IStruct', 'UInt16', 'UInt32', 'UInt64', 'UInt8', 'Float4',
           'Float8', 'bits2bytes', 'handler_from_bit_length',
           'handler_from_int', 'handler_from_byte_length',
           'StringHandler', 'BytesHandler', 'int_selector']


class IStruct(PyStruct):

    def size(self, bytes_string=None):
        return super().size

    def unpack(self, bytes_string):
        return super().unpack(bytes_string)[0]

    def unpack_from(self, bytes_string):
        return super().unpack_from(bytes_string)[0]


UInt32 = IStruct("!I")
UInt16 = IStruct("!H")
UInt64 = IStruct("!Q")
UInt8 = IStruct("!B")
Float4 = IStruct("!f")
Float8 = IStruct("!d")

int_packers = [UInt8, UInt16, UInt32, UInt64]
int_sized = {x.size(): x for x in int_packers}


def bits2bytes(bits):
    return ceil(bits / 8)


def handler_from_byte_length(total_bytes):
    """Find the smallest handler needed to pack a number of bytes

    :param total_bytes: number of bytes needed to pack
    :rtype: :py:class:`network.serialiser.IStruct`"""
    for packer in int_packers:
        if packer.size() >= total_bytes:
            break
    else:
        raise ValueError("Integer too large to pack")

    return packer


def handler_from_int(value):
    return handler_from_bit_length(value.bit_length())


def handler_from_bit_length(total_bits):
    total_bytes = bits2bytes(total_bits)
    return handler_from_byte_length(total_bytes)


class BoolHandler:
    unpacker = UInt8.unpack_from

    @classmethod
    def unpack_from(cls, bytes_string):
        return bool(cls.unpacker(bytes_string))

    size = UInt8.size
    pack = UInt8.pack


class BytesHandler:

    def __init__(self, static_value):
        header_max_value = static_value.data.get("max_length", 255)
        self.packer = handler_from_int(header_max_value)

    def pack(self, bytes_string):
        return self.packer.pack(len(bytes_string)) + bytes_string

    def size(self, bytes_string):
        length = self.packer.unpack_from(bytes_string)
        return length + self.packer.size()

    def unpack(self, bytes_string):
        return bytes_string[self.packer.size():]

    def unpack_from(self, bytes_string):
        length = self.size(bytes_string)
        return self.unpack(bytes_string[:length])


class StringHandler(BytesHandler):

    def pack(self, str_):
        return super().pack(str_.encode())

    def unpack(self, bytes_string):
        return super().unpack(bytes_string).decode()


def int_selector(type_flag):
    if "max_value" in type_flag.data:
        return handler_from_int(type_flag.data["max_value"])

    return handler_from_bit_length(type_flag.data.get('max_bits', 8))


def float_selector(type_flag):
    return Float8 if type_flag.data.get("max_precision") else Float4

# Register handlers for native types
register_handler(bool, BoolHandler)
register_handler(str, StringHandler, is_callable=True)
register_handler(bytes, BytesHandler, is_callable=True)
register_handler(int, int_selector, is_callable=True)
register_handler(float, float_selector, is_callable=True)
