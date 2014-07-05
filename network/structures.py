from copy import deepcopy
from functools import wraps

__all__ = ['factory_dict', 'TypedList', 'TypedSet']


def copy_operation(operation):
    """Effects an operation upon a copy of a TypedIterable instance"""
    @wraps(operation)
    def wrapper(self, arg):
        new = self.copy()
        operation(new, arg)
        return new

    return wrapper


def mutable_operation(operation):
    """Effects an operation in-place upon a TypedIterable instance"""
    @wraps(operation)
    def wrapper(self, arg):
        operation(self, arg)
        return self

    return wrapper


def factory_dict(factory_function, dict_type=dict, provide_key=True):
    """Produces a dictionary object with default values for missing keys

    :param factory_function: function to create value for missing key
    :param dict_type: base class for returned dictionary
    :param provide_key: provide the factory function with the missing key
    """
    def missing_key(self, key):
        value = self[key] = factory_function(key)
        return value

    def missing(self, key):
        value = self[key] = factory_function()
        return value

    callback = missing_key if provide_key else missing
    dict_cls = type("factory_dict", (dict_type,), {"__missing__": callback})
    return dict_cls()


class TypedIterableBase:
    """Iterable class which ensures every element is validated before addition"""

    def __init__(self, type_=None, iterable=None):
        try:
            self._type = type_ or iterable._type

        except AttributeError as err:
            raise TypeError("{} requires type or typed iterable in arguments".format(self.__class__.__name__)) from err

        if iterable:
            super().__init__(iterable)

        else:
            super().__init__()

    def __deepcopy__(self, memo):
        return self.__class__(self._type, deepcopy([i for i in self], memo))

    def copy(self):
        return self.__class__(self._type, super().copy())


class TypedList(TypedIterableBase, list):
    """List class with static type checking"""

    def append(self, obj):
        if not isinstance(obj, self._type):
            raise TypeError("Elements must be of type {}".format(self._type))
        super().append(obj)

    def extend(self, obj):
        if not isinstance(obj, TypedIterableBase):
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


class TypedSet(TypedIterableBase, set):
    """Set class with static type checking"""

    def _verify_iterable(self, iterable):
        """Verifies that all members are typed correctly

        :param iterable: iterable to check
        """
        if not isinstance(iterable, TypedIterableBase):
            for element in iterable:
                if not isinstance(element, self._type):
                    raise TypeError("Elements must be of type {}".format(self._type))

        elif iterable._type != self._type:
            raise TypeError("{} must be of the same type".format(self.__class__.__name__))

    def add(self, element):
        if not isinstance(element, self._type):
            raise TypeError("Elements must be of type {}".format(self._type))

        super().add(element)

    def intersection_update(self, other):
        self._verify_iterable(other)

        super().intersection_update(other)

    def symmetric_difference_update(self, other):
        self._verify_iterable(other)

        super().symmetric_difference_update(other)

    def update(self, other):
        self._verify_iterable(other)

        super().update(other)

    __ior__ = mutable_operation(update)
    __ixor__ = mutable_operation(symmetric_difference_update)
    __iand__ = mutable_operation(intersection_update)
    __isub__ = mutable_operation(set.difference_update)

    __or__ = union = copy_operation(update)
    __xor__ = symmetric_difference = copy_operation(symmetric_difference_update)
    __and__ = intersection = copy_operation(intersection_update)
    __sub__ = difference = copy_operation(set.difference_update)
