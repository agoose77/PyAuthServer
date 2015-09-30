from contextlib import contextmanager


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


class ProtectedInstance:

    _is_allowed_creation = False
    creation_path_name = ""

    @classmethod
    @contextmanager
    def _allow_creation(cls):
        is_allowed, cls._is_allowed_creation = cls._is_allowed_creation, True
        yield
        cls._is_allowed_creation = is_allowed

    def __new__(cls, *args, **kwargs):
        if not cls._is_allowed_creation:
            raise RuntimeError("Must instantiate '{}' from '{}'"
                               .format(cls.__name__, cls.creation_path_name))

        return super().__new__(cls)

    @classmethod
    def _create_protected(cls, *args, **kwargs):
        with cls._allow_creation():
            return cls(*args, **kwargs)
