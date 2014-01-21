class TypeRegister(type):
    '''Registers all subclasses of parent class
    Stores class name: class mapping on parent._types'''

    def __new__(self, name, parents, attrs):
        cls = super().__new__(self, name, parents, attrs)

        try:
            cls._types[name] = cls

        except AttributeError:
            cls._types = {}
            func = getattr(cls, "register_type", None)

        else:
            func = getattr(cls, "register_subtype", None)

        if callable(func):
            func()

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
        try:
            return self._types[type_name]
        except KeyError:
            raise LookupError("No class with name {}".format(type_name))
