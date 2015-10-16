from contextlib import contextmanager
from functools import wraps


class NamedSubclassTracker(type):

    def __new__(metacls, name, bases, namespace):
        cls = super().__new__(metacls, name, bases, namespace)

        try:
            subclasses = cls.subclasses

        except AttributeError:
            subclasses = cls.subclasses = {}

        subclasses[name] = cls
        return cls


class UniqueIDPool:

    def __init__(self, bound):
        self.bound = bound
        self._id_set = set(range(bound))

    def retire(self, unique_id):
        self._id_set.add(unique_id)

    def take(self):
        return self._id_set.pop()


def restricted_method(func):
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        if self.__class__._is_restricted:
            raise RuntimeError("Cannot call protected method")

        return func.__get__(self, self.__class__)(*args, **kwargs)

    return wrapper


def restricted_new(func):
    @wraps(func)
    def wrapper(cls, *args, **kwargs):
        if cls._is_restricted:
            raise RuntimeError("Cannot call protected method")

        return func.__get__(cls)(*args, **kwargs)

    return wrapper


class ProtectedInstance:

    _is_restricted = True

    @classmethod
    @contextmanager
    def _grant_authority(cls):
        is_restricted, cls._is_restricted = cls._is_restricted, False
        yield
        cls._is_restricted = is_restricted

    @restricted_new
    def __new__(cls, *args, **kwargs):
        return super().__new__(cls)
