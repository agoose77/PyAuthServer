from .type_register import TypeRegister
from .world_info import WorldInfo

__all__ = ['NetmodeDelegateMeta']


class TaggedDelegateMeta(metaclass=TypeRegister):
    """Provides an interface to select a subclass by a tag value"""

    def __new__(cls, *args, **kwargs):
        tag = cls.get_current_tag()
        delegated_class = cls.find_subclass_for(tag)

        return super().__new__(delegated_class)

    @staticmethod
    def get_current_tag():
        raise NotImplementedError()

    @classmethod
    def find_subclass_for(cls, tag_value):
        """Find subclass with a tag value

        :param tag_value: value of tag to isolate
        """
        try:
            subclasses = cls.subclasses

        except AttributeError:
            raise TypeError("This class does not implement a subclass dictionary")

        for subclass in subclasses.values():

            if getattr(subclass, "_tag", None) == tag_value:
                return subclass

        raise TypeError("Tag: {} is not supported by this class".format(tag_value))


class NetmodeDelegateMeta(TaggedDelegateMeta):

    @staticmethod
    def get_current_tag():
        return WorldInfo.netmode

# TODO make this more generic
# Delegate actor definition for env
# Create from file