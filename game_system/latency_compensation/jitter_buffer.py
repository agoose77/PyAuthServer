__all__ = "JitterBuffer",


class JitterBuffer:

    def __init__(self, length, margin=None):
        """
        :param length: number of entries required to allow item retrieval
        :param margin: tolerance to overfill, default to length
        """
        self._length = length

        if margin is None:
            margin = length

        self._margin = margin

        self._total_length = length + margin
        self._buffer = [None] * self._total_length

        self._is_filling = True
        self._valid_items = 0
        self._index = 0

    @property
    def is_filling(self):
        return self._is_filling

    def push(self, data, id_):
        index = id_ % self._total_length

        if not self._valid_items:
            self._index = index

        # Check that we've not already pushed this item
        current_item = self._buffer[index]
        if current_item is not None:
            _, current_id = current_item

            # We've tried to add the same item
            if id_ == current_id:
                raise KeyError("Item already in buffer")

            # We've hit the head of the buffer
            elif current_id < id_:
                self._index = (self._index + 1) % self._total_length

        # Check that the item we wish to push isn't too old
        pending_read_item = self._buffer[self._index % self._total_length]
        if pending_read_item is not None:
            _, last_id = pending_read_item

            if id_ <= last_id:
                raise KeyError("Item expired")

        self._buffer[index] = (data, id_)
        self._valid_items += 1

        if self._valid_items >= self._length:
            self._is_filling = False

    def __iter__(self):
        return self

    def __next__(self):
        if self._is_filling:
            raise StopIteration("Buffer filling")

        read_index = self._index
        item, self._buffer[read_index] = self._buffer[read_index], None

        # Update index
        self._index = (read_index + 1) % self._total_length

        if item is None:
            raise ValueError("Found unfilled member slot")

        self._valid_items -= 1

        if not self._valid_items:
            self._is_filling = True

        return item

    def __len__(self):
        return self._valid_items

    def __bool__(self):
        return bool(self._valid_items)

    def __repr__(self):
        return ''.join(["X" if item is not None else "_" for item in self._buffer])