__all__ = ["is_reliable", "is_simulated", "is_annotatable", "has_annotation"]

"""API Helper functions for internal operations"""


def is_reliable(func):
    """Determines if a function is replicated reliably

    :param func: function to __call__
    :returns: result of condition
    """
    return func.__annotations__.get("reliable", False)


def is_simulated(func):
    """Determine if a function is marked as simulated

    :param func: function to __call__
    :returns: result of condition
    """
    return func.__annotations__.get("simulated", False)


def is_annotatable(func):
    """Determine if function may be given annotations

    :param func: function to test
    :returns: result of condition
    """
    return hasattr(func, "__annotations__")


def has_annotation(name):
    """Create annotation decorator that looks for a value in a function's annotations

    :param name: name of annotation
    """
    def wrapper(func):
        try:
            annotations = func.__annotations__

        except AttributeError:
            return False

        return name in annotations

    return wrapper


