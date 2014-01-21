from copy import deepcopy
from .handler_interfaces import static_description

__all__ = ['TypeFlag', 'Attribute']


class TypeFlag:
    '''Container for static-type values
    holds type for value and additional keyword arguments
    Pretty printable'''
    __slots__ = ['type', 'data']

    def __init__(self, type_, **kwargs):
        self.type = type_
        self.data = kwargs

    def __repr__(self):
        return "<TypeFlag: type={}>".format(self.type)


class Attribute(TypeFlag):
    __slots__ = ["notify", "complain", "name", "_instances", "_value"]

    def __init__(self, value=None, type_of=None,
                 notify=False, complain=False, **kwargs):

        super().__init__(type_of or type(value), **kwargs)

        self.notify = notify
        self.complain = complain

        self.name = None

        self._instances = {}
        self._value = value

    def __get__(self, instance, base):
        # Try and get value, or register to instance
        try:
            storage_interface = self._instances[instance]
        except KeyError:
            return self

        try:
            return storage_interface.value

        except AttributeError:
            return self

    def __set__(self, instance, value):
        storage_interface = self._instances[instance]

        # Get the last value
        last_value = storage_interface.value

        # Avoid executing unnecessary logic
        if last_value == value:
            return

        # If the attribute should complain
        if self.complain:
            # Register a complain with value description
            storage_interface.set_complaint(static_description(value))

        # Force type check
        if value is not None and not isinstance(value, self.type):
            raise TypeError("{}: Cannot set value to {} value"
                            .format(self, value.__class__.__name__))

        # Store value
        storage_interface.value = value

    def __repr__(self):
        return "<Attribute {}: type={.__name__}>".format(self.name, self.type)

    def register(self, instance, storage_interface):
        '''Registers attribute for instance'''
        self._instances[instance] = storage_interface

    def get_new_value(self):
        return deepcopy(self._value)
