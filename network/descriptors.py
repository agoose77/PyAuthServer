from copy import deepcopy

from .handlers import static_description
from .structures import factory_dict
from .type_flag import TypeFlag

__all__ = ['TypeFlag', 'Attribute', 'DescriptorFactory']


class Attribute(TypeFlag):
    """Container for static-type values"""

    __slots__ = ["notify", "complain", "name", "_instances", "initial_value"]

    def __init__(self, value=None, data_type=None, notify=False, complain=False, **kwargs):
        super().__init__(data_type or type(value), **kwargs)

        self.notify = notify
        self.complain = complain
        self.initial_value = value

        self.name = None

        self._instances = {}

    def __get__(self, instance, base):
        # Try and get value, or register to instance
        if instance is None:
            return self

        storage_interface = instance.__dict__[self]
        return storage_interface.get()

    def __set__(self, instance, value):
        storage_interface = instance.__dict__[self]

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
        if value is not None and not isinstance(value, self.data_type):
            raise TypeError("{}: Cannot set value to {} value" .format(self, value.__class__.__name__))

        # Store value
        storage_interface.set(value)

    def __repr__(self):
        return "<Attribute {}: type={.__name__}>".format(self.name, self.data_type)

    def register(self, instance, storage_interface):
        """Registers attribute for instance"""
        instance.__dict__[self] = storage_interface

    def get_new_value(self):
        """Return copy of initial value"""
        if self.initial_value is None:
            return None

        return deepcopy(self.initial_value)


class DescriptorFactory:
    """Factory for class descriptors"""

    def __init__(self, callback):
        self.callback = callback

    def __get__(self, instance, base):
        if instance is None:
            return self

        instance_dict = instance.__dict__

        try:
            return instance_dict[self]

        except KeyError:
            result = self.callback(instance)
            instance_dict[self] = result

            return result
