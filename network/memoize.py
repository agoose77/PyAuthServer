from functools import partial, update_wrapper


def Memoizable(cls):
    slots = list(cls.__slots__) + ["_cache"]
    return type(cls.__name__, (cls,), {"__slots__": slots})


class Memoize:

    def __init__(self, func):
        update_wrapper(self, func)
        self.func = func

    def __get__(self, obj, objtype=None):
        if obj is None:
            return self.func
        return partial(self, obj)

    def __call__(self, *args, **kw):
        obj = args[0]

        try:
            cache = obj._cache
        except AttributeError:
            cache = obj._cache = {}

        key = (self.func, args[1:], frozenset(kw.items()))
        try:
            res = cache[key]

        except KeyError:
            res = cache[key] = self.func(*args, **kw)
        return res
