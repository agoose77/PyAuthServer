from collections import OrderedDict

from network.factory import SubclassRegistryMeta
from network.replication import Serialisable, SerialisableDataStoreDescriptor


def is_serialisable(obj):
    return isinstance(obj, Serialisable)


class StructMetacls(SubclassRegistryMeta):

    @classmethod
    def is_not_root(metacls, bases):
        for base_cls in bases:
            if isinstance(base_cls, metacls):
                return True

        return False

    def __prepare__(name, bases):
        return OrderedDict()

    def __new__(metacls, name, bases, namespace):
        serialisable_data = namespace['serialisable_data'] = SerialisableDataStoreDescriptor()
        serialisables = serialisable_data.serialisables

        # Inherit from parent classes
        for cls in reversed(bases):
            if not isinstance(cls, metacls):
                continue

            serialisable_data.extend(cls.serialisable_data)

        # Register serialisables, including parent-class members
        for attr_name, value in namespace.items():
            if attr_name.startswith("__"):
                continue

            if isinstance(value, Serialisable):
                value.name = attr_name
                serialisables[attr_name] = value

        return super().__new__(metacls, name, bases, namespace)


class Struct(metaclass=StructMetacls):

    def __new__(cls, *args, **kwargs):
        self = super().__new__(cls)
        cls.serialisable_data.bind_instance(self)

        return self

    def __init__(self, **kwargs):
        for name, value in kwargs.items():
            setattr(self, name, value)

    def __deepcopy__(self, memodict):
        return self.from_list(self.to_list())

    def to_list(self):
        data = self.serialisable_data
        return [data[s] for s in self.__class__.serialisable_data.serialisables.values()]

    def update_list(self, values):
        data = self.serialisable_data

        for serialisable, value in zip(self.__class__.serialisable_data.serialisables.values(), values):
            data[serialisable] = value

        return self

    @classmethod
    def from_list(cls, values):
        self = cls.__new__(cls)
        self.update_list(values)
        return self

    def __repr__(self):
        as_string = ", ".join(("{}={}".format(s.name, v) for s, v in self.serialisable_data.items()))
        return "{}({})".format(self.__class__.__name__, as_string)
