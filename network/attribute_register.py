from .containers import AttributeStorageContainer
from .descriptors import DescriptorFactory


class AttributeMeta(type):
    """Creates Attribute storage interface for each class type"""

    def __new__(self, name, bases, attrs):
        cls = super().__new__(self, name, bases, attrs)

        attributes = AttributeStorageContainer.get_member_instances(cls)
        ordered_attributes = AttributeStorageContainer.get_ordered_members(
                                                                   attributes)

        cls._attribute_container = DescriptorFactory(
                    AttributeStorageContainer, attributes, ordered_attributes)

        return cls
