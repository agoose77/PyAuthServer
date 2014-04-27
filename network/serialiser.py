from struct import Struct as PyStruct
from math import ceil

from .handler_interfaces import register_handler

__all__ = ['IStruct', 'UInt16', 'UInt32', 'UInt64', 'UInt8', 'Float4',
           'Float8', 'bits2bytes', 'handler_from_bit_length',
           'handler_from_int', 'handler_from_byte_length',
           'StringHandler', 'BytesHandler', 'int_selector']


class IStruct(PyStruct):

    def size(self, bytes_=None):
        return super().size

    def unpack(self, bytes_):
        return super().unpack(bytes_)[0]

    def unpack_from(self, bytes_):
        return super().unpack_from(bytes_)[0]


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


class BytesHandler:

    def __init__(self, static_value):
        header_max_value = static_value.data.get("max_length", 255)
        self.packer = handler_from_int(header_max_value)

    def pack(self, bytes_):
        return self.packer.pack(len(bytes_)) + bytes_

    def size(self, bytes_):
        length = self.packer.unpack_from(bytes_)
        return length + self.packer.size()

    def unpack(self, bytes_):
        return bytes_[self.packer.size():]

    def unpack_from(self, bytes_):
        length = self.size(bytes_)
        return self.unpack(bytes_[:length])


class StringHandler(BytesHandler):

    def pack(self, str_):
        return super().pack(str_.encode())

    def unpack(self, bytes_):
        return super().unpack(bytes_).decode()


def int_selector(type_flag):
    if "max_value" in type_flag.data:
        return handler_from_int(type_flag.data["max_value"])

    return handler_from_bit_length(type_flag.data.get('max_bits', 8))

# Register handlers for native types
register_handler(str, StringHandler, is_condition=True)
register_handler(bytes, BytesHandler, is_condition=True)
register_handler(int, int_selector, is_condition=True)
register_handler(float, lambda x: (Float8 if x.data.get("max_precision")
                                   else Float4), is_condition=True)
