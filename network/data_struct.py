from .containers import AttributeStorageContainer
from .flag_serialiser import FlagSerialiser

from copy import deepcopy

__all__ = ['Struct']


class Struct:
    """Serialisable object with individual fields"""

    def __init__(self):
        self._container = AttributeStorageContainer(self)
        self._container.register_storage_interfaces()
        self._serialiser = FlagSerialiser(self._container._ordered_mapping)

    def __deepcopy__(self, memo):
        new_struct = self.__class__()

        for name, member in self._container._ordered_mapping.items():
            old_value = self._container.data[member]
            new_member = new_struct._container.get_member_by_name(name)
            new_struct._container.data[new_member] = deepcopy(old_value)

        return new_struct

    def __description__(self):
        return hash(self._container.get_description_tuple())

    def to_bytes(self):
        return self._serialiser.pack({a.name: v for a, v in
                                      self._container.data.items()})

    def to_tuple(self):
        container = self._container
        attributes = container._ordered_mapping.values()
        data = container.data
        return tuple(data[k] for k in attributes)

    def from_tuple(self, tuple_):
        for member, value in zip(
                         self._container._ordered_mapping.values(), tuple_):
            self._data[member] = value

    def on_notify(self, name):
        pass

    def from_bytes(self, bytes_):
        notifications = []

        replicable_data = self._container.data
        get_attribute = self._container.get_member_by_name

        # Process and store new values
        for attribute_name, value in self._serialiser.unpack(bytes_,
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

    def __repr__(self):
        attribute_count = len(self._container.data)
        return "<Struct {}: {} member{}>".format(self.__class__.__name__,
                                                 attribute_count, 's' if
                                                 attribute_count != 1 else '')
