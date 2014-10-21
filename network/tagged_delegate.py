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
    def update_cache(cls, from_cls=None):
        try:
            subclasses = cls.subclasses

        except AttributeError:
            if from_cls is None:
                raise TypeError("Subclass dictionary was not implemented by {}".format(cls.type_name))

            else:
                return

        cls._cache.update({get_tag(c): c for c in subclasses.values() if has_tag(c)})

        try:
            parent = next(c for c in cls.__mro__[1:] if getattr(c, "subclasses", subclasses) is not subclasses)

        except StopIteration:
            pass

        else:
            parent.update_cache(from_cls=cls)

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
        if delegated_class.is_delegate:
            return delegated_class.__new__(delegated_class, *args, **kwargs)

        return super().__new__(delegated_class)

    @classmethod
    def register_type(cls):
        super().register_type()

        cls.is_delegate = True

    @classmethod
    def register_subtype(cls):
        super().register_subtype()

        cls.is_delegate = False

    @staticmethod
    def get_current_tag():
        raise NotImplementedError()


class DelegateByNetmode(DelegateByTag):

    @staticmethod
    def get_current_tag():
        return WorldInfo.netmode
