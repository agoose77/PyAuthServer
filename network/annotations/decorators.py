from functools import wraps, update_wrapper
from inspect import getmembers

from .conditions import is_simulated, is_annotatable
from ..enums import Roles


__all__ = ['reliable', 'simulated', 'requires_netmode', 'ignore_arguments', 'set_annotation', 'set_annotation',
           'get_annotation', 'IgnoredArgumentsDescriptor', 'simulate_methods', 'protected', 'requires_permission']


"""API functions to modify function behaviour"""


def set_annotation(name):
    """Create annotation decorator that assigns a value to a function's annotations

    :param name: name of annotation
    """
    def outer(value):
        def inner(func):
            try:
                annotations = func.__annotations__

            except AttributeError:
                annotations = func.__annotations__ = {}

            annotations[name] = value

            return func

        return inner

    return outer


def get_annotation(name, default=None, modify=False):
    """Create annotation decorator that returns a value from a function's annotations

    :param name: name of annotation
    :param default: default value if not found
    :param modify: create value if not found
    """
    def wrapper(func):
        try:
            annotations = func.__annotations__

        except AttributeError:
            return None

        if modify:
            return annotations.setdefault(name, default)

        return annotations.get(name, default)

    return wrapper


def reliable(func):
    """Mark a function to be reliably replicated

    :param func: function to be marked
    :returns: function that was passed as func
    """
    return set_annotation("reliable")(True)(func)


def simulated(func):
    """Mark a function to be a simulated function

    :param func: function to be marked
    :returns: function that was passed as func
    """
    return set_annotation("simulated")(True)(func)


def requires_netmode(netmode):
    """Create a decorator that marks a class as requiring the provided netmode context before execution

    :param netmode: netmode required to execute function
    :requires: provided :py:attr:`network.world_info._WorldInfo.netmode` context
    :returns: decorator that prohibits function execution for incorrect netmode
    """

    def wrapper(func):
        @wraps(func)
        def _wrapper(self, *args, **kwargs):
            if self.scene.world.netmode != netmode:
                return

            bound_func = func.__get__(self, self.__class__)
            return bound_func(*args, **kwargs)

        return _wrapper

    return wrapper


def requires_permission(func):
    """Create a closure decorator that marks a class as requiring the provided netmode context before execution

    :requires: provided :py:attr:`network.replicable.Replicable` class defines a valid :py:attr:`network.enums.Roles`
    network Role
    :returns: decorator that prohibits function execution for incorrect role
    """
    simulated_proxy = Roles.simulated_proxy
    func_is_simulated = is_simulated(func)

    @wraps(func)
    def wrapper(self, *args, **kwargs):
        # Check that the assumed instance/class has roles
        try:
            arg_roles = self.roles

        except AttributeError as err:
            raise AttributeError("Class instance must define roles attribute") from err

        # Check that the roles are of an instance
        local_role = arg_roles.local

        # Permission checks
        if local_role > simulated_proxy or (func_is_simulated and local_role == simulated_proxy):
            return func.__get__(self, self.__class__)(*args, **kwargs)

    return wrapper


class IgnoredArgumentsDescriptor:
    """Descriptor for stripping arguments from function call"""

    def __init__(self, func):
        update_wrapper(self, func)

        self._func = func
        self._is_descriptor = isinstance(self._func, (staticmethod, classmethod))

    def __call__(self, *args, **kwargs):
        self._func()

    def __get__(self, instance, owner):
        bound_func = self._func.__get__(instance, owner)

        def wrapper(*args, **kwargs):
            return bound_func()

        return wrapper


def ignore_arguments(func):
    """Create a closure decorator that calls decorated function without arguments

    :param func: function to decorate
    :returns: decorated function
    """
    return IgnoredArgumentsDescriptor(func)


def simulate_methods(cls):
    """Mark all member methods as simulated

    :param cls: class to decorate
    :returns: cls
    """
    for name, member in getmembers(cls):
        if not is_annotatable(member):
            continue

        simulated(member)

    return cls


def protected(func):
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        if self.__class__._is_restricted:
            raise RuntimeError("Cannot call protected method")

        return func.__get__(self, self.__class__)(*args, **kwargs)

    return wrapper

