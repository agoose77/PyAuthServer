from bge_network.sorted_collection import SortedCollection

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

    def __bool__(self):
        return not self._filling

    def __len__(self):
        return len(self._buffer)

    def append(self, item):
        self._buffer.insert(item)

        if self._filling and len(self._buffer) > self.length:
            filled_callback = self.on_filled
            if callable(filled_callback):
                filled_callback()

            self._filling = False

        buffer_length = self.length * 2
        total_items = len(self._buffer)

        # Remove excess items
        if total_items > buffer_length:
            remove_item = self._buffer.remove
            for i in range(total_items, buffer_length):
                remove_item(self[i])

    def check_for_lost_item(self, item, previous_item):
        get_id_func = self._get_id

        if get_id_func is None or previous_item is None:
            return False

        result_id = get_id_func(item)
        previous_id = get_id_func(previous_item)

        if (result_id - previous_id) > 1:
            lost_items = result_id - previous_id - 1
            message = "items were" if lost_items > 1 else "item was"
            print("{} {} lost, attempting to recover one item".format(lost_items, message))
            return True

        return False

    def clear(self):
        self._buffer.clear()

    def find_lost_item(self, item, previous_item):
        recover_previous = self._recover_previous

        if recover_previous is None:
            return item

        self.append(item)
        # Make recovery
        return recover_previous(item)

    def pop(self):
        if self._filling:
            return None

        result = self._buffer[0]
        self._buffer.remove(result)
        previous_item = self._previous_item

        # Account for lost items
        if previous_item is not None:
            lost_item = self.check_for_lost_item(result, previous_item)
            if lost_item:
                self.append(result)
                result = self.find_lost_item(result, previous_item)

        self._previous_item = result

        if not self._buffer:
            empty_callback = self.on_empty
            if callable(empty_callback):
                empty_callback()

            self._filling = True

        return result
