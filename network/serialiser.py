from struct import Struct as PyStruct
from math import ceil

from .handler_interfaces import register_handler


class IStruct(PyStruct):
    def size(self, bytes_=None):
        return super().size

    def unpack(self, bytes_):
        return super().unpack(bytes_)[0]

    def unpack_from(self, bytes_):
        return super().unpack_from(bytes_)[0]


UInt32 = IStruct("@I")
UInt16 = IStruct("@H")
UInt64 = IStruct("@L")
UInt8 = IStruct("@B")
Float4 = IStruct("@f")
Float8 = IStruct("@d")

int_packers = [UInt8, UInt16, UInt32, UInt64]
int_sized = {x.size(): x for x in int_packers}


def bits2bytes(bits):
    return ceil(bits / 8)


def handler_from_bit_length(bits):
    bytes_ = bits2bytes(bits)
    return int_sized[bytes_]


def handler_from_int(value):
    return handler_from_bit_length(value.bit_length())


def handler_from_byte_length(bytes_):
    return int_sized[bytes_]


class String:
    packer = UInt8

    @classmethod
    def pack(cls, str_):
        return cls.packer.pack(len(str_)) + str_.encode()

    @classmethod
    def size(cls, bytes_):
        length = cls.packer.unpack_from(bytes_)
        return length + 1

    @classmethod
    def unpack(cls, bytes_):
        return bytes_[cls.packer.size():].decode()

    @classmethod
    def unpack_from(cls, bytes_):
        length = cls.size(bytes_)
        return cls.unpack(bytes_[:length])


# Register handlers for native types
register_handler(str, String)
register_handler(int, lambda x: handler_from_int(x.data.get("max_value", 8)),
                 is_condition=True)
register_handler(float, lambda x: (Float8 if x.data.get("max_precision")
                                   else Float4), is_condition=True)
