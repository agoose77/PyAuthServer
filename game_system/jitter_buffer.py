from network.logger import logger

from .sorted_collection import SortedCollection

__all__ = ["JitterBuffer"]


class JitterBuffer:

    def __init__(self, max_length, full_length, on_discontinuity=None):
        self.highest_inserted_index = -1
        self.last_read_index = -1
        self.last_read_item = None

        self.just_inserted = False

        self._buffer = [None] * max_length
        self.max_length = max_length
        self.full_length = full_length

        self._filling = True
        self._length = 0

        self._on_discontinuity = on_discontinuity

    def __len__(self):
        return self._length

    def __bool__(self):
        return not self._filling

    def __getitem__(self, index):
        index_ = (self.last_read_index + 1 + index) % self.max_length
        return self._buffer[index_]

    def insert(self, key, value):
        # Last read item
        max_length = self.max_length

        base_item = self._buffer[self.highest_inserted_index]

        # If exhausted all items, first insert
        if not self.just_inserted and self._filling:
            insert_index = 0
            self.last_read_index = -1
            self.last_read_item = None

        # Insert according to the base read key
        else:
            try:
                insert_offset = key - base_item[0]
            except TypeError:
                print(self._buffer, key, self.highest_inserted_index)
                import bge;bge.logic.endGame()
            insert_index = (self.highest_inserted_index + insert_offset) % max_length

        # Get reading data
        last_read_index = self.last_read_index
        next_read_index = (last_read_index + 1) % max_length

        # If we hit the full index after successive fill operations, stop filling
        if self.just_inserted:
            # If we are filling from empty
            if insert_index == (self.full_length - 1):
                self._filling = False

            # If the next read is at the last insertion
            elif insert_index == next_read_index:
                self.last_read_index = insert_index
                self.last_read_item = (key, value)

        # Used to mark successive insert operations (before reads)
        self.just_inserted = True

        # If this is a newer insert
        last_inserted = self._buffer[self.highest_inserted_index]
        if not (last_inserted and last_inserted[0] > key):
            self.highest_inserted_index = insert_index

        self._buffer[insert_index] = key, value
        self._length += 1

    def popitem(self):
        if self._filling:
            raise ValueError("Buffer is filling")

        last_read_index = self.last_read_index
        last_insert_index = self.highest_inserted_index
        buffer = self._buffer

        # Read index
        read_index = (last_read_index + 1) % self.max_length

        # This is a read operation
        if self.just_inserted:
            self.just_inserted = False

        # If we have already read into the last inserted item
        elif read_index == last_insert_index:
            self._filling = True

        # Read item from buffer
        read_item = buffer[read_index]

        # Find missing item!
        if read_item is None:
            # Handle discontinuity
            if callable(self._on_discontinuity):
                # If we recovered some moves
                if self.recover_discontinuity(read_index):
                    return self.popitem()

            raise ValueError("Discontinuous buffer")

        # Read was valid
        self._length -= 1

        self.last_read_index = read_index
        self.last_read_item = read_item

        buffer[read_index] = None

        return read_item

    def recover_discontinuity(self, read_index):
        buffer = self._buffer
        max_length = self.max_length
        last_item = self.last_read_item

        # Fast forward to next item
        read_item = buffer[(read_index + 1) % max_length]
        while read_item is None:
            read_item = buffer[(read_index + 1) % max_length]

        # Recover items
        insert = self.insert
        recovered = self._on_discontinuity(last_item, read_item)

        if recovered:
            last_read_index = self.last_read_index
            for key, value in recovered:
                insert(key, value)

            self.last_read_index = last_read_index

        return bool(recovered)


class JitterBuffer_:
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
