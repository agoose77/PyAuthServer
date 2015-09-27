__all__ = "EnumerationMeta",


class _EnumDict(dict):

    def __init__(self, autonum):
        super().__init__()

        self._member_names = []
        self._autonum = autonum
        self._has_real_values = False

    def __setitem__(self, name, value):
        if name.startswith("__"):
            return super().__setitem__(name, value)

        if name in self._member_names:
            raise ValueError("'{}' is already a member of '{}' Enum".format(name, self.__class__.__name__))

        # Auto numbering
        if value is Ellipsis:
            if self._has_real_values:
                raise SyntaxError("An implicit definition cannot follow an explicit one")

            value = self._autonum(len(self._member_names))

        # Int values
        elif isinstance(value, int):
            if self._member_names and not self._has_real_values:
                print(self._member_names, value)
                raise SyntaxError("An explicit definition cannot follow an implicit one")

            self._has_real_values = True

        else:
            super().__setitem__(name, value)

        self._member_names.append(name)
        super().__setitem__(name, value)


def default_numbering(i):
    return i


# For scene:
#   scene has channels
#   create generic parser (id->payload - maybe nested packet? - packet is a subclass of ProtocolPayload?)
#       write to/from containers with a container_stream
#   use generic ID for scene, name is local data, sent on replication
#   create event system (?) or have a replication command for creating scene


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