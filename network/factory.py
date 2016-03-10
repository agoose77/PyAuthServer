from collections import deque
from contextlib import contextmanager


class SubclassRegistryMeta(type):

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
        self._id_deque = deque(range(bound))

    def retire(self, unique_id):
        if unique_id in self._id_deque:
            raise ValueError("ID already retired: '{}'".format(unique_id))

        self._id_deque.append(unique_id)

    def take(self, unique_id=None):
        if unique_id is None:
            unique_id = self._id_deque.popleft()

        else:
            try:
                self._id_deque.remove(unique_id)
            except ValueError as err:
                raise ValueError("ID already in use: '{}'".format(unique_id)) from err

        return unique_id


class ProtectedInstanceMeta(type):

    _is_restricted = True

    def __call__(cls, *args, **kwargs):
        if cls._is_restricted:
            raise RuntimeError("Cannot call protected method")

        return super().__call__(*args, **kwargs)

    @contextmanager
    def _grant_authority(cls):
        is_restricted, cls._is_restricted = cls._is_restricted, False
        yield
        cls._is_restricted = is_restricted
