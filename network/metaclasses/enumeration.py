__all__ = "EnumerationMeta",


class _EnumDict(dict):

    def __init__(self, autonum):
        super().__init__()

        self._member_names = []
        self._autonum = autonum

    def __setitem__(self, name, value):
        if name.startswith("__"):
            return super().__setitem__(name, value)

        if name in self._member_names:
            raise ValueError("'{}' is already a member of '{}' Enum".format(name, self.__class__.__name__))

        # Auto numbering
        if value is Ellipsis:
            value = self._autonum(len(self._member_names))

        self._member_names.append(name)
        super().__setitem__(name, value)


def default_numbering(i):
    return i


class EnumerationMeta(type):
    """Metaclass for Enumerations in Python"""

    def __init__(metacls, name, bases, namespace, autonum=None):
        super().__init__(name, bases, namespace)

    def __new__(metacls, name, bases, namespace, autonum=None):
        identifiers = namespace._member_names

        # Return new class
        cls = super().__new__(metacls, name, bases, namespace)

        cls.identifiers = tuple(identifiers)
        cls._values_to_identifiers = {namespace[n]: n for n in identifiers}

        return cls

    @classmethod
    def __prepare__(metacls, name, bases, autonum=default_numbering, **kwargs):
        return _EnumDict(autonum)

    def __getitem__(cls, value):
        # Add ability to lookup name
        return cls._values_to_identifiers[value]

    def __contains__(cls, index):
        return index in cls.identifiers

    def __len__(cls):
        return len(cls.identifiers)

    def __iter__(cls):
        namespace = cls.__dict__
        return ((k, namespace[k]) for k in cls.identifiers)