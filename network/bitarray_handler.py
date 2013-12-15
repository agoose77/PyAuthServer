from bitarray import Bitfield
from .serialiser import (handler_from_byte_length, handler_from_bit_length,
                         bits2bytes)
from .handler_interfaces import register_handler, get_handler
from .descriptors import StaticValue


class BitarrayInt:

    size_packer = get_handler(StaticValue(int))

    @classmethod
    def pack(cls, field):
        # Get the smallest needed packer for this bitfield
        packed_size = cls.size_packer.pack(len(field))
        return packed_size + field.tobytes()

    @classmethod
    def unpack(cls, bytes_):
        field_size = cls.size_packer.unpack_from(bytes_)

        field = Bitfield()
        off = cls.size_packer.size()
        field.frombytes(bytes_[off:off + field_size])
        return field

    @classmethod
    def unpack_merge(cls, field_, bytes_):
        field_[:] = cls.unpack(bytes_)

    unpack_from = unpack

    @classmethod
    def size(cls, bytes_):
        field_size = cls.size_packer.unpack_from(bytes_)
        return bits2bytes(field_size) + cls.size_packer.size()

#register_handler(Bitfield, BitarrayInt)