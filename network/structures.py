from copy import deepcopy

__all__ = ['FactoryDict', 'TypedList', 'TypedSet']


def operation_to_copy(operation):
    """Effects an operation upon a copy of a TypedIterable instance"""
    def wrapper(self, arg):
        new = self.copy()
        operation(new, arg)
        return new
    return wrapper


def operation_in_place(operation):
    """Effects an operation in-place upon a TypedIterable instance"""
    def wrapper(self, arg):
        operation(self, arg)
        return self
    return wrapper


def FactoryDict(factory_func, dict_type=dict, provide_key=True):

    def missing_key(self, key):
        value = self[key] = factory_func(key)
        return value

    def missing(self, key):
        value = self[key] = factory_func()
        return value

    callback = missing_key if provide_key else missing

    return type("FactoryDict", (dict_type,), {"__missing__": callback})()



class TypedIterable:

    def __init__(self, type_=None, iterable=None):
        try:
            self._type = type_ or iterable._type

        except AttributeError as err:
            raise TypeError("{} requires type or typed iterable \
            in arguments".format(self.__class__.__name__)) from err

        if iterable:
            super().__init__(iterable)

        else:
            super().__init__()

    def copy(self):
        return self.__class__(self._type, super().copy())

    def __deepcopy__(self, memo):
        return self.__class__(self._type, deepcopy([i for i in self], memo))


class TypedList(TypedIterable, list):

    def append(self, obj):
        if not isinstance(obj, self._type):
            raise TypeError("Elements must be of type {}".format(self._type))
        super().append(obj)

    def extend(self, obj):
        if not isinstance(obj, TypedIterable):
            for elem in obj:
                if not isinstance(elem, self._type):
                    raise TypeError("Elements must be of type {}"
                                    .format(self._type))
        elif obj._type != self._type:
            raise TypeError("{} must be of the same type"
                            .format(self.__class__.__name__))
        super().extend(obj)

    def insert(self, index, obj):
        if not isinstance(obj, self._type):
            raise TypeError("Elements must be of type {}".format(self._type))
        super().insert(index, obj)


class TypedSet(TypedIterable, set):

    def add(self, obj):
        if not isinstance(obj, self._type):
            raise TypeError("Elements must be of type {}".format(self._type))
        super().add(obj)

    def verify_set(self, obj):
        if not isinstance(obj, TypedIterable):
            for elem in obj:
                if not isinstance(elem, self._type):
                    raise TypeError("Elements must be of type {}"
                                    .format(self._type))

        elif obj._type != self._type:
            raise TypeError("{} must be of the same type"
                            .format(self.__class__.__name__))

    def update(self, obj):
        self.verify_set(obj)

        super().update(obj)

    def intersection_update(self, obj):
        self.verify_set(obj)

        super().intersection_update(obj)

    def symmetric_difference_update(self, obj):
        self.verify_set(obj)

        super().symmetric_difference_update(obj)

    def insert(self, index, obj):
        if not isinstance(obj, self._type):
            raise TypeError("Elements must be of type {}".format(self._type))
        super().insert(index, obj)

    __ior__ = operation_in_place(update)
    __ixor__ = operation_in_place(symmetric_difference_update)
    __iand__ = operation_in_place(intersection_update)
    __isub__ = operation_in_place(set.difference_update)

    __or__ = union = operation_to_copy(update)
    __xor__ = symmetric_difference = operation_to_copy(symmetric_difference_update)
    __and__ = intersection = operation_to_copy(intersection_update)
    __sub__ = difference = operation_to_copy(set.difference_update)
