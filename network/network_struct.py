from copy import deepcopy

from .attribute_register import AttributeMeta
from .flag_serialiser import FlagSerialiser

__all__ = ['Struct', 'StructMeta']


class StructMeta(AttributeMeta):
    """Creates serialiser code for class (optimisation)"""

    def __new__(self, name, bases, attrs):
        cls = super().__new__(self, name, bases, attrs)

        ordered_arguments = cls._attribute_container.args[1]
        cls._serialiser = FlagSerialiser(ordered_arguments)
        cls.__slots__ = []

        return cls


class Struct(metaclass=StructMeta):
    """Serialisable object with individual fields"""

    def __init__(self):
        self._attribute_container.register_storage_interfaces()

    def __deepcopy__(self, memo):
        """Serialiser description of tuple

        :returns: new struct instance"""
        new_struct = self.__class__()
        # Local lookups
        old_attribute_container_data = self._attribute_container.data
        new_attribute_container_data = new_struct._attribute_container.data
        get_new_member = new_struct._attribute_container.get_member_by_name

        for name, member in self._attribute_container._ordered_mapping.items():
            old_value = old_attribute_container_data[member]
            new_member = get_new_member(name)
            new_attribute_container_data[new_member] = deepcopy(old_value)

        return new_struct

    def __description__(self):
        """Serialiser description of tuple"""
        return hash(self._attribute_container.get_description_tuple())

    def __repr__(self):
        attribute_count = len(self._attribute_container.data)
        return "<Struct {}: {} member{}>".format(self.__class__.__name__,
                                                 attribute_count, 's' if
                                                 attribute_count != 1 else '')

    @classmethod
    def from_bytes(cls, bytes_string):
        """Create a struct from bytes

        :param bytes_string: Packed byte representation of struct contents
        :returns: Struct instance"""
        struct = cls()
        struct.read_bytes(bytes_string)

        return struct

    @classmethod
    def from_tuple(cls, tuple_):
        """Create a struct from a tuple

        :param tuple_: Tuple representation of struct contents
        :returns: Struct instance"""
        struct = cls()
        struct.read_tuple(tuple_)

        return struct

    def read_bytes(self, bytes_string):
        """Update struct contents with bytes

        :param bytes_string: Packed byte representation of struct contents"""
        notifications = []

        replicable_data = self._attribute_container.data
        get_attribute = self._attribute_container.get_member_by_name

        # Process and store new values
        for attribute_name, value in self._serialiser.unpack(bytes_string,
                                                    replicable_data):
            attribute = get_attribute(attribute_name)
            # Store new value
            replicable_data[attribute] = value

            # Check if needs notification
            if attribute.notify:
                notifications.append(attribute_name)

        # Notify after all values are set
        if notifications:
            for attribute_name in notifications:
                self.on_notify(attribute_name)

    def read_tuple(self, tuple_):
        """Update struct contents with a tuple

        :param tuple_: Tuple representation of struct contents"""
        data = self._attribute_container.data
        members = self._attribute_container._ordered_mapping.values()

        for member, value in zip(members, tuple_):
            data[member] = value

    def to_bytes(self):
        """Write struct contents to bytes

        :returns: packed contents"""
        return self._serialiser.pack({a.name: v for a, v in
                                      self._attribute_container.data.items()})

    def to_tuple(self):
        """Write struct contents to a tuple

        :returns: contents tuple"""
        container = self._attribute_container
        attributes = container._ordered_mapping.values()
        data = container.data
        return tuple(data[k] for k in attributes)

    def on_notify(self, name):
        pass
