from .serialiser import bits2bytes

class Bitfield:
	@classmethod
	def from_iterable(cls, iterable):
		size = len(iterable)
		field = Bitfield(size)
		field[:size] = iterable
		return field

	@classmethod
	def of_length(cls, size):
		return cls(size)

	def __init__(self, size, value=0):
		self._size = size
		self._value = value

		self.footprint = bits2bytes(size)

	def __iter__(self):
		return self[:].__iter__()

	def __bool__(self):
		return self._value > 0

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

	def clear(self):
		self._value = 0

	def resize(self, size):
		self._size = size
		self.footprint = bits2bytes(self._size)
