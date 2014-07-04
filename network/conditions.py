from inspect import isfunction

__all__ = ["is_reliable", "is_simulated", "is_signal_listener", "is_annotatable", "is_class_method",
           "is_instance_method", "is_static_method"]

"""API Helper functions for internal operations"""


def is_class_method(cls, name):
    """Determine if function is a class method of given class

    :param cls: class with function
    :param name: name of function
    """
    return isinstance(cls.__dict__[name], classmethod)


def is_static_method(cls, name):
    """Determine if function is a static method of given class

    :param cls: class with function
    :param name: name of function
    """
    return isinstance(cls.__dict__[name], staticmethod)


def is_instance_method(cls, name):
    """Determine if function is an instance method of given class

    :param cls: class with function
    :param name: name of function
    """
    return isfunction(cls.__dict__[name])


def is_reliable(func):
    """Determines if a function is replicated reliably

    :param func: function to evaluate
    :returns: result of condition
    """
    return func.__annotations__.get("reliable", False)


def is_simulated(func):
    """Determine if a function is marked as simulated

    :param func: function to evaluate
    :returns: result of condition
    """
    return func.__annotations__.get("simulated", False)


def is_signal_listener(func):
    """Determine if a function is a signal listener

    :param func: function to evaluate
    :returns: result of condition
    """
    return "signals" in func.__annotations__


def is_annotatable(func):
    """Determine if function may be given annotations

    :param func: function to test
    :returns: result of condition
    """
    return hasattr(func, "__annotations__")