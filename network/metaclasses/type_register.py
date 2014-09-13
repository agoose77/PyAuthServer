class _TypeRegisterBase:

    @classmethod
    def register_subtype(cls):
        pass

    @classmethod
    def register_type(cls):
        pass


class TypeRegister(type):
    """Registers all subclasses of parent class
    Stores class name: class mapping on parent.subclasses
    """

    def __new__(meta, name, parents, attributes):
        parents += (_TypeRegisterBase,)

        cls = super().__new__(meta, name, parents, attributes)

        try:
            subclasses = cls.subclasses

        except AttributeError:
            return cls

        # Register as a sub-type of parent
        parent = cls.__mro__[1]
        if hasattr(parent, "subclasses"):
            subclasses[name] = cls

            cls.register_subtype()

        # Otherwise we're a parent type
        else:
            cls.register_type()

        return cls

    @property
    def type_name(cls):
        return cls.__name__

    def from_type_name(self, type_name):
        """Get class type from type_name

        :param type_name: name of class type
        :returns: class reference
        """
        try:
            return self.subclasses[type_name]

        except KeyError:
            raise LookupError("No class with name {} can be found in this subclass tree".format(type_name))

        except AttributeError:
            raise TypeError("This class does not implement a subclass dictionary")
