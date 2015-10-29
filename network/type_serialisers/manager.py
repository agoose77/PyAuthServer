from contextlib import contextmanager
from logging import getLogger

serialisers = {}
describers = {}

__all__ = ['get_describer', 'register_serialiser', 'register_describer', 'get_serialiser', 'default_logger_as',
           'TypeSerialiserAbstract', 'TypeDescriberAbstract']

# Default loggers for handlers, handlers can be a class or an instance, so don't force user to set the logger
_DEFAULT_LOGGER = getLogger("<Default Serialiser Logger>")
LOGGER = _DEFAULT_LOGGER


class TypeInfo:
    """Container for static type information.

    Holds type for value and additional keyword arguments.

    Pretty printable.
    """
    __slots__ = ['data_type', 'data']

    def __init__(self, data_type, **kwargs):
        self.data_type = data_type
        self.data = kwargs

    def __repr__(self):
        return "<TypeInfo({}, {})>".format(self.data_type, self.data)


@contextmanager
def default_logger_as(logger):
    global LOGGER
    LOGGER = logger
    yield
    LOGGER = _DEFAULT_LOGGER


def register_serialiser(value_type, handler):
    """Registers new handler for custom serialisers

    :param value_type: type of object
    :param handler: handler object for value_type
    :param is_callable: whether handler should be called with the TypeInfo that
    requests it
    """
    serialisers[value_type] = handler


def register_describer(value_type, describer):
    """Registers description callback for types which cannot define
    __description__
    and are not directly hash-able

    :param value_type: type of object
    :param describer: description function
    """
    describers[value_type] = describer


def get_serialiser(type_info, logger=None):
    """Takes a TypeInfo (or subclass thereof) and return handler.

    If a handler cannot be found for the provided type, look for a handled
    superclass, assign it to the requested type and return it.

    :param type_info: TypeInfo subclass
    :returns: handler object
    """

    value_type = type_info.data_type

    try:
        handler = serialisers[value_type]

    except KeyError:
        try:
            handled_superclasses = (cls for cls in value_type.__mro__ if cls in serialisers)
            handled_type = next(handled_superclasses)

        except StopIteration as err:
            raise TypeError("No handler found for object with type '{}'".format(value_type)) from err

        except AttributeError as err:
            raise TypeError("TypeInfo.data_type: expected class object, not '{}'".format(value_type)) from err

        else:
            # Remember this for later call
            handler = serialisers[value_type] = serialisers[handled_type]

    # Add default logger
    if logger is None:
        logger = LOGGER

    return handler(type_info, logger=logger)


def get_serialiser_for(data_type, logger=None, **data):
    info = TypeInfo(data_type, **data)
    return get_serialiser(info)


def get_describer(type_info):
    value_type = type_info.data_type

    # First handle registered descriptions
    try:
        describer = describers[value_type]

    except KeyError:
        try:
            handled_superclasses = (cls for cls in value_type.__mro__ if cls in describers)
            handled_type = next(handled_superclasses)

        # Default to Python hashing
        except (AttributeError, StopIteration):
            describer = DefaultTypeDescriber

        else:
            describer = describers[handled_type]

    return describer(type_info)


class TypeDescriberAbstract:

    def __init__(self, type_info):
        pass

    def __call__(self, value):
        raise NotImplementedError


class DefaultTypeDescriber(TypeDescriberAbstract):
    __slots__ = ()

    def __call__(self, value):
        try:
            return value.__description__()

        except AttributeError:
            return hash(value)


class TypeSerialiserAbstract:
    supports_mutable_unpacking = False

    def __init__(self, type_info, logger=None):
        pass

    def pack(self, value):
        raise NotImplementedError

    def pack_multiple(self, values, count):
        raise NotImplementedError

    def unpack_from(self, bytes_string, offset=0):
        raise NotImplementedError

    def unpack_multiple(self, bytes_string, count, offset=0):
        raise NotImplementedError

    def unpack_merge(self, previous_value, bytes_string, offset=0):
        raise NotImplementedError

    def size(self, bytes_string):
        raise NotImplementedError