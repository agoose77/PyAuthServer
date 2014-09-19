from .decorators import get_tag, has_tag
from .metaclasses import TypeRegister
from .world_info import WorldInfo

__all__ = ['DelegateByNetmode', 'DelegateByTag', 'FindByTag']


class FindByTag(metaclass=TypeRegister):
    """Provides an interface to select a subclass by a tag value"""

    @classmethod
    def register_type(cls):
        cls._cache = {}

    @classmethod
    def update_cache(cls):
        try:
            cache = {get_tag(c): c for c in cls.subclasses.values() if has_tag(c)}

        except AttributeError:
            raise TypeError("Subclass dictionary was not implemented by {}".format(cls.type_name))

        cls._cache.update(cache)

    @classmethod
    def find_subclass_for(cls, tag_value):
        """Find subclass with a tag value

        :param tag_value: value of tag to isolate
        """

        try:
            cache = cls._cache

        except AttributeError:
            raise TypeError("Subclass dictionary was not implemented by {}".format(cls.type_name))

        try:
            return cache[tag_value]

        except KeyError:
            raise TypeError("Tag: {} is not supported by {}".format(tag_value, cls.type_name))


class DelegateByTag(FindByTag):

    def __new__(cls, *args, **kwargs):
        tag = cls.get_current_tag()
        delegated_class = cls.find_subclass_for(tag)

        return super().__new__(delegated_class)

    @staticmethod
    def get_current_tag():
        raise NotImplementedError()


class DelegateByNetmode(DelegateByTag):

    @staticmethod
    def get_current_tag():
        return WorldInfo.netmode
