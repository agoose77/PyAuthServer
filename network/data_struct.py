from .serialiser import UInt8
from .handler_interfaces import register_handler
from .containers import AttributeStorageContainer

from copy import deepcopy

class Struct:
    def __init__(self):
        
        self._container = AttributeStorageContainer(self)
        self._container.register_storage_interfaces()
    
    def __deepcopy__(self, memo):
        new_struct = self.__class__()
        
        for name, member in self._container.get_ordered_members().items():
            old_value = self._container.data[member]
            new_member = new_struct._container.get_member_by_name(name)
            new_struct._container.data[new_member] = deepcopy(old_value)
            
        return new_struct
    
    def __description__(self):
        return self._container.get_complaint_descriptions(self._container.data)
            
    def to_bytes(self):
        return self._container.pack(self._container.data)
    
    def on_notify(self, name):
        pass
    
    def from_bytes(self, bytes_):
        notifier = self.on_notify
        container_data = self._container.data
        
        # Process and store new values
        for attribute, value in self.serialiser.unpack(bytes_, container_data):
            # Store new value
            container_data[attribute] = value
            
            # Check if needs notification
            if attribute.notify:
                notifier(attribute.name)

class StructHandler:
    
    @classmethod
    def pack(cls, struct):
        bytes_ = struct.to_bytes()
        return UInt8.pack(len(bytes_)) + bytes_
    
    @classmethod
    def unpack_merge(cls, struct, bytes_):
        struct.from_bytes(bytes_[1:])
    
    @classmethod
    def size(cls, bytes_):
        return UInt8.unpack_from(bytes_)
    
register_handler(Struct, StructHandler)