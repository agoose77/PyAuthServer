from .containers import RPCStorageContainer
from .descriptors import DescriptorFactory

__all__ = ['RPCMeta']


class RPCMeta(type):
    """Creates RPC storage interface for each class type"""

    def __new__(self, name, bases, attrs):
        cls = super().__new__(self, name, bases, attrs)

        members = RPCStorageContainer.get_member_instances(cls)
        ordered_members = RPCStorageContainer.get_ordered_members(members)

        cls._attribute_container = DescriptorFactory(
                    RPCStorageContainer, members, ordered_members)

        return cls
