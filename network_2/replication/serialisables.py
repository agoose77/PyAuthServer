from ..handlers import TypeFlag, static_description


class SerialisableData:

    def __init__(self):
        self._data_stores = {}

    def __get__(self, instance, owner):
        if instance is None:
            return self

        return self._data_stores[instance]

    def bind_instance(self, instance):
        self._data_stores[instance] = []

    def unbind_instance(self, instance):
        del self._data_stores[instance]


class Serialisable(TypeFlag):

    __slots__ = ("notify", "complain", "initial_value")

    def __init__(self, value=None, data_type=None, notify=False, complain=False, **kwargs):
        if data_type is None:
            if value is None:
                raise TypeError("Serialisable must be given a value or data type different from None")

            data_type = type(value)

        super().__init__(data_type, **kwargs)

        self.notify = notify
        self.complain = complain
        self.initial_value = value

    def __get__(self, instance, cls):
        if instance is None:
            return self

        return instance.serialisables[self]

    def __set__(self, instance, value):
        serialisables = instance.serialisables

        if value is not None and not isinstance(value, self.data_type):
            raise TypeError("{}: Cannot set value to {} value" .format(self, value.__class__.__name__))

        # If the attribute should complain
        if self.complain:
            # Register a complain with value description
            storage_interface.complain(static_description(value))

        serialisables[self] = value
