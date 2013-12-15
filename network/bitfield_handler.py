from .serialiser import (handler_from_byte_length, handler_from_bit_length, bits2bytes)
from .handler_interfaces import register_handler, get_handler
from .descriptors import StaticValue
from .bitfield import Bitfield


class BitfieldInt:

    size_packer = get_handler(StaticValue(int))

    @classmethod
    def pack(cls, field):
        # Get the smallest needed packer for this bitfield
        footprint = field.footprint
        packed_size = cls.size_packer.pack(field._size)

        if footprint:
            field_packer = handler_from_byte_length(footprint)
            return packed_size + field_packer.pack(field._value)
        else:
            return packed_size

    @classmethod
    def unpack(cls, bytes_):
        field_size = cls.size_packer.unpack_from(bytes_)

        if field_size:
            field_packer = handler_from_bit_length(field_size)
            data = field_packer.unpack_from(bytes_[cls.size_packer.size():])
        else:
            data = 0

        field = Bitfield(field_size, data)
        return field

    @classmethod
    def unpack_merge(cls, field, bytes_):
        footprint = field.footprint
        if footprint:
            field_packer = handler_from_byte_length(footprint)
            field._value = field_packer.unpack_from(
                                bytes_[cls.size_packer.size():])

    unpack_from = unpack

    @classmethod
    def size(cls, bytes_):
        field_size = cls.size_packer.unpack_from(bytes_)
        return bits2bytes(field_size) + cls.size_packer.size()

register_handler(Bitfield, BitfieldInt)
