class TypeRegister(type):
    """Registers all subclasses of parent class
    Stores class name: class mapping on parent.subclasses
    """

    def __new__(meta, name, parents, attributes):
        cls = super().__new__(meta, name, parents, attributes)

        try:
            subclasses = cls.subclasses

        except AttributeError:
            return cls

        # Register as a sub-type of parent
        parent = next((c for c in cls.__mro__[1:] if hasattr(c, "subclasses")), None)

        if hasattr(parent, "subclasses"):
            parent.subclasses[name] = cls

            cls.register_subclass()

            if parent.subclasses is not subclasses:
                cls.register_base_class()

        # Otherwise we're a parent type
        else:
            cls.register_base_class()

        return cls

    @property
    def type_name(cls):
        return cls.__name__

    def register_base_class(cls):
        pass

    def register_subclass(cls):
        pass

    def from_type_name(cls, type_name):
        """Get class type from type_name

        :param type_name: name of class type
        :returns: class reference
        """
        try:
            return cls.subclasses[type_name]

        except KeyError:
            raise LookupError("No class with name {} can be found in this subclass tree".format(type_name))

        except AttributeError:
            raise TypeError("This class does not implement a subclass dictionary")
