from collections import namedtuple
from copy import deepcopy

from .handler_interfaces import static_description
from .type_flag import TypeFlag

__all__ = ['TypeFlag', 'Attribute', 'FromClass', 'DescriptorFactory']


FromClass = namedtuple("MarkAttribute", "name")


class Attribute(TypeFlag):

    __slots__ = ["notify", "complain", "name", "_instances", "initial_value"]

    def __init__(self, value=None, type_of=None, notify=False, complain=False, **kwargs):
        super().__init__(type_of or type(value), **kwargs)

        self.notify = notify
        self.complain = complain
        self.initial_value = value

        self.name = None

        self._instances = {}

    def __get__(self, instance, base):
        # Try and get value, or register to instance
        try:
            storage_interface = self._instances[instance]

        except KeyError:
            return self

        return storage_interface.get()

    def __set__(self, instance, value):
        storage_interface = self._instances[instance]

        # Get the last value
        last_value = storage_interface.get()

        # Avoid executing unnecessary logic
        if last_value == value:
            return

        # If the attribute should complain
        if self.complain:
            # Register a complain with value description
            storage_interface.complain(static_description(value))

        # Force type check
        if value is not None and not isinstance(value, self.type):
            raise TypeError("{}: Cannot set value to {} value" .format(self, value.__class__.__name__))

        # Store value
        storage_interface.set(value)

    def __repr__(self):
        return "<Attribute {}: type={.__name__}>".format(self.name, self.type)

    def register(self, instance, storage_interface):
        """Registers attribute for instance"""
        self._instances[instance] = storage_interface

    def get_new_value(self):
        if self.initial_value is None:
            return None

        return deepcopy(self.initial_value)


class DescriptorFactory:
    """Factory for class descriptors"""

    def __init__(self, callback):
        self._lookup = {}

        self.callback = callback

    def __get__(self, instance, base):
        if instance is None:
            return self

        if not instance in self._lookup:
            result = self._lookup[instance] = self.callback(instance)

        else:
            result = self._lookup[instance]

        return result
