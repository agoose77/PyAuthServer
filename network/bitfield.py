from .serialiser import bits2bytes

__all__ = ["BitField"]


class BitField:

    '''BitField data type which supports slicing operations'''

    @classmethod
    def from_iterable(cls, iterable):
        '''Factory function to create a BitField from an iterable object

        :param iterable: source iterable
        :requires: fixed length iterable object
        :returns: BitField instance of length equal to ``len(iterable)``
        ``Bitfield.from_iterable()``'''
        size = len(iterable)
        field = cls(size)
        field[:size] = iterable
        return field

    def __bool__(self):
        return self._value != 0

    def __init__(self, size, value=0):
        self._size = size
        self._value = value

        self.footprint = bits2bytes(size)

    def __iter__(self):
        return (self[i] for i in range(self._size))

    def __getitem__(self,  value):
        if isinstance(value, slice):
            _value = self._value
            return [bool(_value & (1 << index)) for index in
                    range(*value.indices(self._size))]

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
                self._value |= (1 << index)

            else:
                self._value &= ~(1 << index)

    def __len__(self):
        return self._size

    def clear(self):
        """Clears the BitField to zero"""
        self._value = 0

    def resize(self, size):
        """Resizes the BitField

        :param size: new size of BitField instance"""
        self._size = size
        self.footprint = bits2bytes(self._size)
