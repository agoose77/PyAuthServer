from ..containers import AttributeStorageContainer
from ..descriptors import DescriptorFactory

from functools import partial

__all__ = ['AttributeMeta']


class AttributeMeta(type):
    """Creates Attribute storage interface for each class type"""

    def __new__(mcs, name, bases, cls_dict):
        cls = super().__new__(mcs, name, bases, cls_dict)

        attributes = AttributeStorageContainer.get_member_instances(cls)
        ordered_attributes = AttributeStorageContainer.get_ordered_members(attributes)
        factory_callback = partial(AttributeStorageContainer, mapping=attributes, ordered_mapping=ordered_attributes)
        cls._attribute_container = DescriptorFactory(factory_callback)

        return cls
