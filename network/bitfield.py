from math import ceil 

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
        return self._size > 0
    
    def __getitem__(self, index):
        if isinstance(index, slice):
            value = self._value
            start, stop, step = slice.indices(self._size)            
            return [bool(value & (1 << index)) for index in range(start, stop, step)]
        
        else:
            
            if index < 0:
                index += self._size
                
            return bool(self._value & (1 << index))
    
    def __setitem__(self, index, value):
        if isinstance(index, slice):

            for index, slice_value in zip(range(index.start or 0, index.stop or self._size, index.step or 1), value):
                if slice_value:
                    self._value |= 1 << index
                else:
                    self._value &= ~(1 << index)
        
        else:
            if value:
                self._value |= 1 << index
            else:
                self._value &= ~(1 << index)
    
    def clear(self):
        self._value = 0

def bits2bytes(bits):
    return ceil(bits / 8)