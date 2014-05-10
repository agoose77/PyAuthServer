__all__ = ["is_reliable", "is_simulated", "is_signal_listener",
           "is_annotatable", "get_annotation"]

'''API Helper functions for internal operations'''


def is_reliable(func):
    '''Determines if a function is replicated reliably

    :param func: function to evaluate
    :returns: result of condition'''
    return func.__annotations__.get("reliable", False)


def is_simulated(func):
    '''Determines if a function is simulated

    :param func: function to evaluate
    :returns: result of condition'''
    return func.__annotations__.get("simulated", False)


def is_signal_listener(func):
    '''Determines if a function is a signal listener

    :param func: function to evaluate
    :returns: result of condition'''
    return "signals" in func.__annotations__


def is_annotatable(func):
    return hasattr(func, "__annotations__")


def get_annotation(func, name, default=None):
    return func.__annotations__.get(name, default)