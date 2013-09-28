from math import ceil

from .serialiser import (handler_from_byte_length, handler_from_bit_length,
                         bits2bytes)
from .handler_interfaces import register_handler, get_handler
from .descriptors import StaticValue


class Bitfield:

    @classmethod
    def from_iterable(cls, iterable):
        size = len(iterable)
        field = Bitfield(size)
        field[:size] = iterable
        return field

    def __init__(self, size, value=0):
        self._size = size
        self._value = value

        self.footprint = bits2bytes(self._size)

    def __iter__(self):
        return iter(self[:])

    def __bool__(self):
        return self._value > 0

    def __getitem__(self, index):
        if isinstance(index, slice):
            value = self._value
            start, stop, step = index.indices(self._size)
            return [bool(value & (1 << index)) for index in
                    range(*index.indices(self._size))]

        else:
            if index < 0:
                index += self._size

            if index >= self._size:
                raise IndexError("Index out of range")

            return bool(self._value & (1 << index))

    def __setitem__(self, index, value):
        if isinstance(index, slice):

            current_value = self._value

            for shift_depth, slice_value in zip(
                range(*index.indices(self._size)), value):

                if slice_value:
                    current_value |= 1 << shift_depth
                else:
                    current_value &= ~(1 << shift_depth)

            self._value = current_value

        else:
            if index < 0:
                index += self._size

            elif index >= self._size:
                raise IndexError("Index out of range")

            if value:
                self._value |= 1 << index
            else:
                self._value &= ~(1 << index)

    def clear(self):
        self._value = 0


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
            data = field_packer.unpack_from(bytes_[1:])
        else:
            data = 0
        # Assume 8 bits
        field = Bitfield(field_size, data)
        return field

    @classmethod
    def unpack_merge(cls, field, bytes_):
        footprint = field.footprint
        if footprint:
            field_packer = handler_from_byte_length(footprint)
            field._value = field_packer.unpack_from(bytes_[1:])

    unpack_from = unpack

    @classmethod
    def size(cls, bytes_):
        field_size = cls.size_packer.unpack_from(bytes_)
        return bits2bytes(field_size) + cls.size_packer.size()

register_handler(Bitfield, BitfieldInt)
