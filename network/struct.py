from copy import deepcopy

from .metaclasses.struct import StructMeta

__all__ = ['Struct']


class Struct(metaclass=StructMeta):
    """Serialisable object with individual fields"""

    def __init__(self):
        self._attribute_container.register_storage_interfaces()

    def __deepcopy__(self, memo):
        """Serialiser description of tuple

        :returns: new struct instance
        """
        new_struct = self.__class__()
        source_container = self._attribute_container
        target_container = new_struct._attribute_container

        # Local lookups
        old_attribute_container_data = source_container.data
        new_attribute_container_data = target_container.data
        get_new_member = target_container.get_member_by_name

        for name, member in source_container._ordered_mapping.items():
            old_value = old_attribute_container_data[member]
            new_member = get_new_member(name)
            new_attribute_container_data[new_member] = deepcopy(old_value)

        return new_struct

    def __description__(self):
        """Serialiser description of tuple"""
        return hash(self._attribute_container.get_ordered_descriptions())

    def __repr__(self):
        class_name = self.__class__.__name__
        attributes = self._attribute_container.data
        associated_values = "".join(["\n    {} = {}".format(k, v) for k, v in attributes.items()])
        return "<Struct {}>{}".format(class_name, associated_values)

    @classmethod
    def from_bytes(cls, bytes_string, offset=0):
        """Create a struct from bytes

        :param bytes_string: Packed byte representation of struct contents
        :returns: Struct instance
        """
        struct = cls()
        struct.read_bytes(bytes_string, offset)

        return struct

    @classmethod
    def from_list(cls, list_):
        """Create a struct from a list

        :param list_: List representation of struct contents
        :returns: Struct instance
        """
        struct = cls()
        struct.read_list(list_)

        return struct

    def read_bytes(self, bytes_string, offset=0):
        """Update struct contents with bytes

        :param bytes_string: Packed byte representation of struct contents
        :param offset: offset to start reading from
        """
        replicable_data = self._attribute_container.data
        get_attribute = self._attribute_container.get_member_by_name

        # Process and store new values
        for attribute_name, value in self._serialiser.unpack(bytes_string, previous_values=replicable_data,
                                                             offset=offset):
            attribute = get_attribute(attribute_name)
            # Store new value
            replicable_data[attribute] = value

    def read_list(self, list_):
        """Update struct contents with a list

        :param list_: List representation of struct contents
        """
        data = self._attribute_container.data
        members = self._attribute_container._ordered_mapping.values()

        for member, value in zip(members, list_):
            data[member] = value

    def to_bytes(self):
        """Write struct contents to bytes

        :returns: packed contents
        """
        return self._serialiser.pack({a.name: v for a, v in self._attribute_container.data.items()})

    def to_list(self):
        """Write struct contents to a list

        :returns: contents tuple
        """
        attribute_data = self._attribute_container.data
        attributes = self._attribute_container._ordered_mapping.values()
        return [attribute_data[attribute] for attribute in attributes]

    def __iter__(self):
        return iter(self.to_list())

    __bytes__ = to_bytes