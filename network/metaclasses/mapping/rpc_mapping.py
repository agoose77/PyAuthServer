from ...containers import RPCStorageContainer
from ...descriptors import DescriptorFactory

from functools import partial

__all__ = ['RPCMeta']


class RPCMeta(type):
    """Creates RPC storage interface for each class type"""

    def __new__(mcs, name, bases, cls_dict):
        cls = super().__new__(mcs, name, bases, cls_dict)

        members = RPCStorageContainer.get_member_instances(cls)
        ordered_members = RPCStorageContainer.get_ordered_members(members)
        factory_callback = partial(RPCStorageContainer, mapping=members, ordered_mapping=ordered_members)

        cls._rpc_container = DescriptorFactory(factory_callback)
        return cls
