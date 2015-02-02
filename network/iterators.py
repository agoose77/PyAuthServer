from itertools import islice, tee

__all__ = ['RenewableGenerator', 'take_single', 'partition_iterable']


class RenewableGenerator:
    """ID manager

    Provides interface to an generator with a callback to replace on StopIteration
    """
    def __init__(self, renew_func):
        self._renew_func = renew_func
        self._internal = renew_func()

    def renew(self):
        self._internal = self._renew_func()

    def __next__(self):
        try:
            return next(self._internal)

        except StopIteration:
            self.renew()

            return next(self._internal)


def take_single(iterable, default=None, reverse=False):
    """Returns first element from iterable

    :param default: default value if iterable is empty
    :param reverse: reverse the sequence
    :returns first element or default
    """
    if reverse:
        iterable = reversed(list(iterable))
    return next(iter(iterable), default)


def look_ahead(iterable):
    """Returns iterator which yields (i, i+1)th terms"""
    items, successors = tee(iterable, 2)
    return zip(items, islice(successors, 1, None))


def partition_iterable(iterable, length, steps=None):
    """Partitions an iterable into fixed length parts

    :param iterable: iterable object
    :param length: length of slice
    :param steps: number of slices
    :returns: list of partition elements
    """
    if steps is None:
        steps = len(iterable)

    return [iterable[i * length: (i + 1 ) * length] for i in range(steps)]