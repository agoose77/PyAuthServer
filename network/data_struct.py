from .serialiser import UInt8
from .handler_interfaces import register_handler
from .containers import AttributeStorageContainer
from .argument_serialiser import ArgumentSerialiser

from copy import deepcopy

class Struct:
    def __init__(self):
        
        self._container = AttributeStorageContainer(self)
        self._container.register_storage_interfaces()
        self._ordered_members = self._container.get_ordered_members()
        self._serialiser = ArgumentSerialiser(self._ordered_members)
    
    def __deepcopy__(self, memo):
        new_struct = self.__class__()
        
        for name, member in self._ordered_members.items():
            old_value = self._container.data[member]
            new_member = new_struct._container.get_member_by_name(name)
            new_struct._container.data[new_member] = deepcopy(old_value)
            
        return new_struct
    
    def __description__(self):
        return hash(tuple(self._container.get_complaint_descriptions(self._container.data).values()))
            
    def to_bytes(self):
        return self._serialiser.pack({a.name: v for a, v in self._container.data.items()})
    
    def on_notify(self, name):
        pass
    
    def from_bytes(self, bytes_):
        notifier = self.on_notify
        container_data = self._container.data
        get_attribute = self._container.get_member_by_name
        
        # Process and store new values
        for attribute_name, value in self._serialiser.unpack(bytes_, container_data):
            
            attribute = get_attribute(attribute_name)
            
            # Store new value
            container_data[attribute] = value
            
            # Check if needs notification
            if attribute.notify:
                notifier(attribute_name)

class StructHandler:
    
    struct_cls = None
    
    @classmethod
    def callback(cls, static_value):
        handler = cls()
        handler.struct_cls = static_value.type
        return handler
    
    def pack(self, struct):
        bytes_ = struct.to_bytes()
        return UInt8.pack(len(bytes_)) + bytes_
    
    def unpack_from(self, bytes_):
        struct = self.struct_cls()
        self.unpack_merge(struct, bytes_)
        return struct
    
    def unpack_merge(self, struct, bytes_):
        struct.from_bytes(bytes_[1:])
    
    def size(self, bytes_):
        return UInt8.unpack_from(bytes_)
    
register_handler(Struct, StructHandler.callback, True)