from .handler_interfaces import register_handler, get_handler
from .descriptors import StaticValue
from .containers import AttributeStorageContainer
from .argument_serialiser import ArgumentSerialiser
from .events import ReplicationNotifyEvent, EventListener

from copy import deepcopy


class Struct(EventListener):
    def __init__(self):
        super().__init__()

        self._container = AttributeStorageContainer(self)
        self._container.register_storage_interfaces()
        self._ordered_members = self._container.get_ordered_members()
        self._serialiser = ArgumentSerialiser(self._ordered_members)

        self.listen_for_events()

    def __deepcopy__(self, memo):
        new_struct = self.__class__()

        for name, member in self._ordered_members.items():
            old_value = self._container.data[member]
            new_member = new_struct._container.get_member_by_name(name)
            new_struct._container.data[new_member] = deepcopy(old_value)

        return new_struct

    def __description__(self):
        return hash(tuple(self._container.get_descriptions(
                                   self._container.data).values()))

    def to_bytes(self):
        return self._serialiser.pack({a.name: v for a, v in \
                                      self._container.data.items()})

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
                ReplicationNotifyEvent.invoke(attribute_name, target=self)


class StructHandler:

    def __init__(self, static_value):
        self.struct_cls = static_value.type
        self.size_packer = get_handler(StaticValue(int))

    def pack(self, struct):
        bytes_ = struct.to_bytes()
        return self.size_packer.pack(len(bytes_)) + bytes_

    def unpack_from(self, bytes_):
        struct = self.struct_cls()
        self.unpack_merge(struct, bytes_)
        return struct

    def unpack_merge(self, struct, bytes_):
        struct.from_bytes(bytes_[self.size_packer.size():])

    def size(self, bytes_):
        return self.size_packer.unpack_from(bytes_) + self.size_packer.size()


register_handler(Struct, StructHandler, True)
