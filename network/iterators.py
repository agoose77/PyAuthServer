__all__ = ['RenewableGenerator', 'take_first']


class RenewableGenerator:
    """ID manager

    Provides interface to an generator with a \
    callback to replace on StopIteration"""
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


def take_first(iterable):
    return next(iter(iterable)) 