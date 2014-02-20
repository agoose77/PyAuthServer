handlers = {}
descriptions = {}

__all__ = ['static_description', 'register_handler', 'register_description',
           'get_handler']


def static_description(obj):
    '''Uses hash-like comparison of muteable and/or immuteable data
    :param obj: object to describe
    :return: obj's hash'''
    if hasattr(obj, "__description__") and hasattr(obj.__description__,
                                                   "__self__"):
        return obj.__description__()

    value_type = type(obj)

    if not value_type in descriptions:
        handled_superclasses = (cls for cls in value_type.__mro__
                                if cls in descriptions)

        try:
            value_type = next(handled_superclasses)

        except StopIteration:
            return hash(obj)

        else:
            # Remember this for later call
            descriptions[type(obj)] = descriptions[value_type]

    return descriptions[value_type](obj)


def register_handler(type_, callable_, is_condition=False):
    '''Registers new handler for custom serialisers
    :param type_: type of object
    :param callable: callable to run
    :param is_condition: whether callable is generic or requires object'''
    handlers[type_] = callable_, is_condition


def register_description(type_, callback):
    '''Registers special description for non-subclass-able types
    :param type_: type of object
    :param callable: callable for description'''
    descriptions[type_] = callback


def get_handler(value):
    def _get_handler(value):
        '''Takes a TypeFlag (or subclass thereof) and return handler
        :param value: TypeFlag subclass'''
    
        value_type = value.type
    
        try:
            callback, is_callable = handlers[value_type]
    
        except KeyError:
            handled_superclasses = (cls for cls in value.type.__mro__
                                    if cls in handlers)
    
            try:
                value_type = next(handled_superclasses)
    
            except StopIteration:
                raise TypeError("No handler found for object with type {}".format(
                                                                    value.type))
            else:
                # Remember this for later call
                callback, is_callable = handlers[value.type] = handlers[value_type]
    
        return callback(value) if is_callable else callback
    try:
        return _get_handler(value)
    except Exception:
        print(value, id(value.type))
