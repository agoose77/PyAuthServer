from bitarray import Bitfield as array_field
from .handler_interfaces import get_handler
from .descriptors import TypeFlag
from .serialiser import bits_to_bytes, next_or_equal_power_of_two

__all__ = ["BitField", "CBitField", "PyBitField"]


class CBitField(array_field):

    @classmethod
    def from_iterable(cls, iterable):
        """Factory function to create a BitField from an iterable object

        :param iterable: source iterable
        :requires: fixed length iterable object
        :returns: BitField instance of length equal to ``len(iterable)``
        ``Bitfield.from_iterable()``"""
        return cls(iterable)

    def __bool__(self):
        return any(self)

    def __new__(cls, other=None):
        if isinstance(other, int):
            other = [False] * other

        inst = super().__new__(cls, other)

        return inst

    def __getitem__(self,  value):
        result = super().__getitem__(value)
        if isinstance(result, array_field):
            return result.tolist()
        return result

    def __setitem__(self, index, value):
        if isinstance(value, list):
            value = array_field(value)
        return super().__setitem__(index, value)

    @staticmethod
    def calculate_footprint(bits):
        return bits_to_bytes(bits)

    @classmethod
    def from_bytes(cls, length, bytes_string):
        field = cls()
        field_size = bits_to_bytes(length)
        field.frombytes(bytes_string[:field_size])
        field[:] = field[:length]
        return field, field_size

    def clear(self):
        """Clears the BitField to zero"""
        self[:] = array_field([False] * self.length())

    to_bytes = array_field.tobytes

    __len__ = array_field.length


class PyBitField:

    """BitField data type which supports slicing operations"""

    def __bool__(self):
        return self._value != 0

    def __init__(self, size, value=0):
        self._value = value

        self.resize(size)

    def __iter__(self):
        return (self[i] for i in range(self._size))

    def __getitem__(self,  value):
        if isinstance(value, slice):
            _value = self._value
            return [bool(_value & (1 << index)) for index in range(*value.indices(self._size))]

        else:
            # Relative indices
            if value < 0:
                value += self._size

            if value >= self._size:
                raise IndexError("Index out of range")

            return (self._value & (1 << value)) != 0

    def __setitem__(self, index, value):
        if isinstance(index, slice):

            current_value = self._value
            for shift_depth, slice_value in zip(range(*index.indices(self._size)), value):

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
                self._value |= (1 << index)

            else:
                self._value &= ~(1 << index)

    def __len__(self):
        return self._size

    @staticmethod
    def calculate_footprint(bits):
        return next_or_equal_power_of_two(bits_to_bytes(bits))

    @classmethod
    def from_bytes(cls, length, bytes_string):
        field = cls(length)
        field._value, field_size = field._handler.unpack_from(bytes_string)
        return field, field_size

    @classmethod
    def from_iterable(cls, iterable):
        """Factory function to create a BitField from an iterable object

        :param iterable: source iterable
        :requires: fixed length iterable object
        :returns: BitField instance of length equal to ``len(iterable)``
        ``Bitfield.from_iterable()``"""
        size = len(iterable)
        field = cls(size)
        field[:size] = iterable
        return field

    def clear(self):
        """Clears the BitField to zero"""
        self._value = 0

    def resize(self, size):
        """Resizes the BitField

        :param size: new size of BitField instance"""
        self._size = size
        self._handler = get_handler(TypeFlag(int, max_bits=size))

    def to_bytes(self):
        """Represent bitfield as bytes"""
        return self._handler.pack(self._value)


BitField = CBitField