__all__ = ["JitterBuffer"]


class JitterBuffer:

    def __init__(self, length, margin):
        self._length = length
        self._margin = margin

        self._total_length = length + margin
        self.buffer = [None] * self._total_length

        self.filling = True
        self.valid_items = 0
        self.index = 0

    def push(self, data, id_):
        index = id_ % self._total_length

        if not self.valid_items:
            self.index = index

        self.buffer[index] = data
        self.valid_items += 1

        if self.valid_items >= self._length:
            self.filling = False

    def __iter__(self):
        return self

    def __next__(self):
        if self.filling:
            raise StopIteration("Buffer filling")

        item, self.buffer[self.index] = self.buffer[self.index], None

        # Update index
        self.index = (self.index + 1) % self._total_length

        if item is None:
            raise ValueError("Found unfilled member slot")

        self.valid_items -= 1

        if not self.valid_items:
            self.filling = True

        return item