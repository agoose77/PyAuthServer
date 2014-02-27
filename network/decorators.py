from functools import wraps

__all__ = ['reliable', 'simulated', 'signal_listener',
           'requires_netmode', 'netmode_switch']


'''API functions to modify function behaviour'''


def annotate(name, value=True):
    def wrapper(func):
        func.__annotations__[name] = value
        return func
    return wrapper


def reliable(func):
    '''Mark a function to be reliably replicated

    :param func: function to be marked
    :returns: function that was passed as func'''
    return annotate("reliable", True)(func)


def simulated(func):
    '''Mark a function to be a simulated function

    :param func: function to be marked
    :returns: function that was passed as func'''
    return annotate("simulated", True)(func)


def signal_listener(signal_type, global_listener):
    '''Curries arguments to create a decorator that marks the
    function as a signal listener

    :param signal_type: signal class
    :param global_listener: flag that allows global invocation
    :returns: decorator function'''
    def wrapper(func):
        signals = func.__annotations__.setdefault('signals', [])
        signals.append((signal_type, not global_listener))
        return func
    return wrapper


def requires_netmode(netmode):
    '''Curries arguments to create a decorator that marks a class as'''\
    ''' requiring the provided netmode context before execution

    :param netmode: netmode required to execute function
    :requires: provided :py:attr:`network.replicables._WorldInfo.netmode`
    context
    :returns: decorator that prohibits function execution
    for incorrect netmodes'''

    def wrapper(func):
        from .replicables import WorldInfo

        @wraps(func)
        def _wrapper(*args, **kwargs):
            if WorldInfo.netmode != netmode:
                return
            return func(*args, **kwargs)
        return _wrapper
    return wrapper


def netmode_switch(netmode):
    '''Curries arguments to create a decorator that marks a class as
    belonging to a specific netmode context

    :param netmode: netmode that the class belongs to
    :requires: provided netmode context
    :returns: decorator that prohibits function execution
    for incorrect netmodes'''
    def wrapper(cls):
        cls._netmode = netmode

        return cls
    return wrapper

