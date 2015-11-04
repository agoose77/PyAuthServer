__all__ = ["BidirectionalIterator"]


class BidirectionalIterator:
    """Two directional iterator

    Converts sequence to tuple internally
    """

    def __init__(self, sequence, step=1):
        """Initialise iterator

        :param sequence: iterable sequence, converted to tuple unless provided as such
        :param step: step for each iteration
        """
        if not isinstance(sequence, tuple):
            sequence = tuple(sequence)

        self._sequence = tuple(sequence)
        self._index = None
        self.step = step

    @property
    def reversed(self):
        """Return reversed iterator"""
        iterator = BidirectionalIterator(self._sequence, step=-1)
        iterator.index = self.index
        return iterator

    @property
    def index(self):
        return self._index

    @index.setter
    def index(self, value):
        self._index = value % len(self._sequence)

    def __iter__(self):
        return self

    def __next__(self):
        try:
            step = self.step

            if self.index is None:
                self.index = 0 if step > 0 else -1

            else:
                current_index = self._index
                next_index = self._index + step

                if current_index >= 0 > next_index and step < 0:
                    raise StopIteration

                elif step > 0 and next_index >= len(self._sequence):
                    raise StopIteration

                self._index = next_index

            result = self._sequence[self.index]

        except IndexError:
            raise StopIteration

        return result

    def __prev__(self):
        self.index -= 1
        if self.index < 0:
            raise StopIteration

        return self._sequence[self.index]
