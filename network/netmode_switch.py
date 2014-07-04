from .type_register import TypeRegister
from .world_info import WorldInfo

__all__ = ['TaggedDelegateMeta']


class TaggedDelegateMeta(metaclass=TypeRegister):

    """Provides an interface to select a subclass by a tag value"""

    def __new__(cls, *args, **kwargs):
        delegated_class = cls.find_subclass_for(WorldInfo.netmode)

        return super().__new__(delegated_class)

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
