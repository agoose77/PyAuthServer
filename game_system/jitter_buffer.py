from network.logger import logger

from .sorted_collection import SortedCollection

__all__ = ["JitterBuffer"]


class JitterBfuffer:

    def __init__(self, length, soft_overflow=True, id_getter=None, recovery_getter=None, maximum_length=None):
        self.minimum_length = length
        self.maximum_length = maximum_length or round(self.minimum_length * 2.5)

        self._index = None
        self._buffer = [None] * self.maximum_length
        self._valid_items = 0

        self.on_filled = None
        self.on_empty = None

        self._previous_item = None
        self._recover_previous = recovery_getter

        self._get_id = id_getter
        self._soft_overflow = soft_overflow

        self._previous_item = None
        self.base_index = 0
        self.base_id = None

    def __bool__(self):
        return self.readable_items != 0

    def __len__(self):
        return self.readable_items

    def __getitem__(self, index):
        readable_items = self.readable_items
        maximum_length = self.maximum_length

        if self._index is None:
            raise ValueError("Buffer cannot be read from whilst filling")

        if isinstance(index, slice):
            start, stop, step = index.indices(readable_items)

            buffer = self._buffer
            start_index = self._index

            indices = range(start, min(readable_items, stop), step)
            return [buffer[start_index + (i % maximum_length)] for i in indices]

        if index >= readable_items:
            raise IndexError("Buffer index {} out of range".format(index))

        return self._buffer[self._index + (index % maximum_length)]

    def __setitem__(self, index, value):
        writeable_items = self.readable_items

        if self._index is None:
            raise ValueError("Buffer cannot be written to whilst filling")

        if isinstance(index, slice):
            start, stop, step = index.indices(writeable_items)
            iterable = iter(value)

            maximum_length = self.maximum_length
            buffer = self._buffer

            indices = range(start, min(writeable_items, stop), step)
            for i, value in zip(indices, iterable):
                index = i % maximum_length
                buffer[index] = value

        if index >= writeable_items:
            raise IndexError("Buffer index {} out of range".format(index))

        self._buffer[index % self.maximum_length] = value

    def __str__(self):
        delimited_contents = ", ".join(str(x) for x in self[:])
        return "Jitter Buffer: [{}]".format(delimited_contents)

    def _handle_for_missing_items(self, previous_item):
        next_item = self._get_next_valid_item()

        if next_item is None:
            return

        next_id = self._get_id(next_item)
        previous_id = self._get_id(previous_item)

        if next_id < previous_id:
            return

        recovered_moves = self._recover_moves(previous_item, next_item)
        if not recovered_moves:
            return

        for move in reversed(recovered_moves):
            self.insert(move)

        return move

    def _on_empty(self):
        """Internal dispatcher for emptied event"""
        emptied_callback = self.on_empty
        if emptied_callback is not None:
            emptied_callback()

    def _on_filled(self):
        """Internal dispatcher for filled event"""
        filled_callback = self.on_filled
        if filled_callback is not None:
            filled_callback()

    def _set_filling(self):
        """Set the index to None, causing the filling attribute to return True"""
        self._index = None
        self.base_index = 0
        self.base_id = None

    def _set_next_index(self):
        """Increment the internal index

         If the index is out of bounds, wrap around
         """
        self._index = (self._index + 1) % self.maximum_length

    def _get_next_valid_item(self):
        maximum_length = self.maximum_length
        offset = self._index

        for i in range(self.maximum_length):
            next_index = (i + offset) % maximum_length
            next_item = self._buffer[next_index]

            if next_item is not None:
                return next_item

    def _get_overflow_offset(self, index):
        """Determine the minimum offset required to accomodate index

        :param index: out of bounds index
        """
        return (self.maximum_length - index) + 1

    def _fast_forward_index(self, offset):
        """Move the internal index to account for overflow

        :param index: lookup index
        """
        for i in range(offset):
            self._set_next_index()

    def _recover_moves(self, previous_move, next_move):
        recover_previous = self._recover_previous
        if recover_previous is None:
            return None

        # Make recovery
        return recover_previous(previous_move, next_move)

    @property
    def filling(self):
        return self._index is None

    @property
    def readable_items(self):
        return min(self.minimum_length, self._valid_items)

    def clear(self):
        """Mark the buffer as cleared"""
        self._set_filling()
        self._valid_items = 0

    def insert(self, item):
        """Insert an item into the jitter buffer, respecting its ID for sorting

        :param item: item to insert
        """
        has_items = self._valid_items != 0

        identifier = self._get_id(item)

        if self.base_id is None:
            self.base_id = identifier

        insertion_base = self.base_index
        base = self.base_id

        insertion_index = identifier - base

        if insertion_index >= self.maximum_length:

            if not self._soft_overflow:
                raise ValueError("Item ID {} is too far from base {}".format(identifier, base))

            # Determine the amount of overflow and fast forward
            overflow = self._get_overflow_offset(insertion_index)
            insertion_index += overflow

            print("OVERFLOW")

            self._fast_forward_index(overflow)

        buffer_index = (insertion_index + insertion_base) % self.maximum_length

        self._buffer[buffer_index] = item
        self._valid_items += 1

        # When we are refilled, reset the lookup
        if self.filling and self._valid_items >= self.minimum_length:
            self._index = 0
            # Notify any interested parties
            self._on_filled()

    def read_next(self):
        """Read the first item in the buffer and move to the next item"""
        if self.filling:
            return

        # Increment our lookup index
        index = self._index
        self._set_next_index()

        item = self._buffer[index]

        # Recover missing items
        if item is None:
            previous_item = self._previous_item

            if previous_item is not None:
                item = self._handle_for_missing_items(previous_item)

        # Allow recovery to return an item
        if item is not None:
            self._previous_item = item
            self.base_id = self._get_id(item)
            self.base_index = index

            # Consume an item
            self._valid_items -= 1

            # If we cannot remove any more items after this call
            if not self._valid_items:
                # Mark the filling state
                self._set_filling()
                # Notify any interested parties
                self._on_empty()

        self._buffer[index] = None

        return item


class JitterBuffer:
    """Interface for reordering and recovering temporally inconsistent data"""

    def __init__(self, length, id_getter=None, recovery_getter=None, maximum_length=None):
        self.minimum_length = length
        self.maximum_length = maximum_length or round(self.minimum_length * 2.5)

        self._buffer = SortedCollection(key=id_getter)
        self._filling = True

        self.on_filled = None
        self.on_empty = None

        self._previous_item = None
        self._recover_previous = recovery_getter
        self._get_id = id_getter
        self._overflow = False

    def __bool__(self):
        return not self._filling

    def __getitem__(self, index):
        return self._buffer[index]

    def __len__(self):
        return len(self._buffer)

    def check_for_lost_item(self, item, previous_item):
        """Callback to determine whether any items were lost between retrieval

        :param item: newest item
        :param previous_item: previous item in time
        :rtype bool
        """
        get_id_func = self._get_id

        if get_id_func is None or previous_item is None:
            return False

        result_id = get_id_func(item)
        previous_id = get_id_func(previous_item)

        if (result_id - previous_id) > 1:
            lost_items = result_id - previous_id - 1
            message = "items were" if lost_items > 1 else "item was"
            logger.info("{} {} lost, attempting to recover one item".format(lost_items, message))
            return True

        return False

    def clear(self):
        """Clear the buffer of all items"""
        self._buffer.clear()

    def find_lost_items(self, item, previous_item):
        """Recovers missing item(s) between items

        :param item: newest item
        :param previous_item: previous item in time
        """
        recover_previous = self._recover_previous
        if recover_previous is None:
            return None

        # Make recovery
        return recover_previous(previous_item, item)

    def insert(self, item):
        """Insert an item into the buffer

        Inserts item with respect to its ID value

        :param item: item to insert
        """
        buffer = self._buffer
        buffer.insert(item)

        buffer_length = len(buffer)
        maximum_length = self.maximum_length

        if self._filling and buffer_length > self.minimum_length:
            filled_callback = self.on_filled
            if callable(filled_callback):
                filled_callback()

            self._filling = False

        # Remove excess items
        if buffer_length > maximum_length:
            remove_item = buffer.remove
            get_item = buffer.__getitem__

            for i in range(buffer_length - self.minimum_length):
                remove_item(get_item(0))

            # Overflow to prevent recovery
            self._overflow = True

    def read_next(self):
        """Remove and return the newest item in the buffer

        If nothing is found, returns None
        """
        if self._filling:
            return None

        result = self._buffer[0]
        previous_item = self._previous_item
        self._buffer.remove(result)

        # Account for lost items
        can_check_missing_items = previous_item is not None and not self._overflow

        # Perform checks
        if can_check_missing_items and self.check_for_lost_item(result, previous_item):
            missing_items = self.find_lost_items(result, previous_item)

            if missing_items:
                new_result, *remainder = missing_items
                # Add missing items to buffer
                for item in remainder:
                    self.insert(item)
                # We just popped this, return to buffer
                self.insert(result)
                # Take first item
                result = new_result

        # If buffer is empty
        if not self._buffer:
            empty_callback = self.on_empty
            if callable(empty_callback):
                empty_callback()

            self._filling = True

        if result is not None:
            self._previous_item = result

        self._overflow = False

        return result
