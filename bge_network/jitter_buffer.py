from network.logger import logger

from .sorted_collection import SortedCollection

__all__ = ["JitterBuffer"]


class JitterBuffer:

    def __init__(self, length, get_id=None, recover_previous=None):
        self.length = length

        self._buffer = SortedCollection(key=get_id)
        self._filling = True

        self.on_filled = None
        self.on_empty = None

        self._previous_item = None
        self._recover_previous = recover_previous
        self._get_id = get_id
        self._overflow = False

    def __bool__(self):
        return not self._filling

    def __len__(self):
        return len(self._buffer)

    def append(self, item):
        buffer = self._buffer
        buffer.insert(item)

        buffer_length = len(buffer)
        maximum_length = round(self.length * 2.5)

        if self._filling and buffer_length > self.length:
            filled_callback = self.on_filled
            if callable(filled_callback):
                filled_callback()

            self._filling = False

        # Remove excess items
        if buffer_length > maximum_length:
            remove_item = buffer.remove
            get_item = buffer.__getitem__

            for i in range(buffer_length - self.length):
                remove_item(get_item(0))

            # Overflow to prevent recovery
            self._overflow = True

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
        return recover_previous(item, previous_item)

    def pop(self):
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
            if missing_items is not None:
                new_result, *remainder = missing_items
                print([x.id for x in missing_items], [previous_item.id, result.id])
                # Add missing items to buffer
                for item in remainder:
                    self.append(item)
                # We just popped this, return to buffer
                self.append(result)
                # Take first item
                result = new_result

        # If buffer is empty
        if not self._buffer:
            empty_callback = self.on_empty
            if callable(empty_callback):
                empty_callback()

            self._filling = True

        self._previous_item = result
        self._overflow = False

        return result
