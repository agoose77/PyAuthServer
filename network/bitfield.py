from .handlers import get_handler
from .type_flag import TypeFlag
from .serialiser import bits_to_bytes, next_or_equal_power_of_two

__all__ = ["BitField"]

USE_BITARRAY = False

if USE_BITARRAY:
    from bitarray import bitarray as array_field

    class BitField(array_field):

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

        __len__ = array_field.length

        def clear(self):
            """Clears the BitField to zero"""
            self[:] = array_field([False] * self.length())

        @classmethod
        def from_bytes(cls, length, bytes_string, offset=0):
            field = cls()
            field_size = bits_to_bytes(length)
            field.frombytes(bytes_string[offset: offset + field_size])
            field[:] = field[:length]
            return field, field_size

        @classmethod
        def from_iterable(cls, iterable):
            """Factory function to create a BitField from an iterable object

            :param iterable: source iterable
            :requires: fixed length iterable object
            :returns: BitField instance of length equal to ``len(iterable)``
            ``Bitfield.from_iterable()``"""
            return cls(iterable)

        calculate_footprint = staticmethod(bits_to_bytes)
        to_bytes = array_field.tobytes

else:
    class BitField:

        """BitField data type which supports slicing operations"""

        def __init__(self, size, value=0):
            self._value = value

            self.resize(size)

        def __bool__(self):
            return self._value != 0

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

        def __iter__(self):
            return (self[i] for i in range(self._size))

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

        @property
        def size(self):
            return self._size

        @staticmethod
        def calculate_footprint(bits):
            """Return minimum number of bytes required to encode a number of bits

            :param bits: number of bits to be encoded
            """
            return next_or_equal_power_of_two(bits_to_bytes(bits))

        @classmethod
        def from_bytes(cls, length, bytes_string, offset=0):
            """Factory function to create a BitField object of a known length from a string of bytes

            :param length: number of bits in field
            :param bytes_string: encoded data from :py:meth:`BitField.to_bytes()`
            """
            field = cls(length)
            field._value, field_size = field._handler.unpack_from(bytes_string, offset)
            return field, field_size

        @classmethod
        def from_iterable(cls, iterable):
            """Factory function to create a BitField from an iterable object

            :param iterable: source iterable
            :requires: fixed length iterable object
            :returns: BitField instance of length equal to ``len(iterable)``
            """
            size = len(iterable)
            field = cls(size)
            field[:size] = iterable
            return field

        def clear(self):
            """Clear the BitField values to zero
            """
            self._value = 0

        def resize(self, size):
            """Resize the BitField

            :param size: new size of BitField instance
            """
            self._size = size
            self._handler = get_handler(TypeFlag(int, max_bits=size))

        def to_bytes(self):
            """Represent bitfield as bytes"""
            return self._handler.pack(self._value)