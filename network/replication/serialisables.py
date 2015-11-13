from collections import OrderedDict
from copy import deepcopy
from weakref import WeakKeyDictionary

from ..type_serialisers import TypeInfo


class SerialisableDataStoreDescriptor:

    def __init__(self):
        self._data_stores = WeakKeyDictionary()
        self.serialisables = OrderedDict()

    def __get__(self, instance, cls):
        if instance is None:
            return self

        return self._data_stores[instance]

    def extend(self, data_store_descriptor):
        serialisables = self.serialisables
        for name, serialisable in data_store_descriptor.serialisables.items():
            serialisables[name] = serialisable

    def bind_instance(self, instance):
        self._data_stores[instance] = self._initialise_data_store()

    def unbind_instance(self, instance):
        del self._data_stores[instance]

    def _initialise_data_store(self):
        data_store = OrderedDict()

        for serialisable in self.serialisables.values():
            data_store[serialisable] = deepcopy(serialisable.initial_value)

        return data_store


class Serialisable(TypeInfo):
    """Serialisable data attribute"""

    __slots__ = ("notify_on_replicated", "initial_value", "name")

    def __init__(self, value=None, data_type=None, notify_on_replicated=False, **kwargs):
        if data_type is None:
            if value is None:
                raise TypeError("Serialisable must be given a value or data type different from None")

            data_type = type(value)

        super().__init__(data_type, **kwargs)

        self.notify_on_replicated = notify_on_replicated
        self.initial_value = value
        self.name = "<invalid>"

    def __get__(self, instance, cls):
        if instance is None:
            return self

        return instance.serialisable_data[self]

    def __set__(self, instance, value):
        if value is not None and not isinstance(value, self.data_type):
            raise TypeError("{}: Cannot set value to {} value" .format(self, value.__class__.__name__))

        instance.serialisable_data[self] = value

    def __repr__(self):
        return "<Serialisable '{}'>".format(self.name)
