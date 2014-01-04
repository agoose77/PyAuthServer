class TypeRegister(type):
    '''Registers all subclasses of parent class
    Stores class name: class mapping on parent._types'''

    def __new__(self, name, parents, attrs):
        cls = super().__new__(self, name, parents, attrs)

        if not hasattr(cls, "_types"):
            cls._types = []

            if hasattr(cls, "register_type"):
                cls.register_type()

        else:
            cls._types.append(cls)

            if hasattr(cls, "register_subtype"):
                cls.register_subtype()

        return cls

    @property
    def type_name(self):
        '''Property
        Gets the class type name
        @return: name of class type'''
        return self.__name__

    def from_type_name(self, type_name):
        '''Gets class type from type_name
        @param type_name: name of class type
        @return: class reference'''
        for cls in self._types:
            if cls.__name__ == type_name:
                return cls

        raise LookupError("No class with name {}".format(type_name))
