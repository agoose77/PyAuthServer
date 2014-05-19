class TypeRegister(type):
    """Registers all subclasses of parent class
    Stores class name: class mapping on parent.subclasses"""

    def __new__(self, name, parents, attrs):
        cls = super().__new__(self, name, parents, attrs)

        try:
            subclasses = cls.subclasses

        except AttributeError:
            return cls

        # Register as a sub-type of parent
        for parent in cls.__mro__[1:]:
            if hasattr(parent, "subclasses"):
                subclasses[name] = cls
                if hasattr(cls, "register_subtype"):
                    cls.register_subtype()

        # Otherwise we're a parent type
        else:
            if hasattr(cls, "register_type"):
                cls.register_type()

        return cls

    @property
    def type_name(self):
        """Property
        Gets the class type name

        :returns: name of class type"""
        return self.__name__

    def from_type_name(self, type_name):
        """Gets class type from type_name

        :param type_name: name of class type
        :returns: class reference"""
        try:
            return self.subclasses[type_name]
        except KeyError:
            raise LookupError("No class with name {}".format(type_name))
        except AttributeError:
            raise TypeError("This class is not included in the subclass tree")
