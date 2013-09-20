from functools import wraps


def reliable(func):
    func.__annotations__['reliable'] = True
    return func


def simulated(func):
    func.__annotations__['simulated'] = True
    return func


def is_reliable(func):
    return func.__annotations__.get("reliable", False)


def is_simulated(func):
    return func.__annotations__.get("simulated", False)


def is_event(func):
    return "event" in func.__annotations__


class run_on:
    '''Runs method in netmode specific scope only'''

    def __init__(self, netmode):
        self.netmode = netmode
        from .actors import WorldInfo
        self._system_info = WorldInfo

    def __call__(self, func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if self._system_info.netmode != self.netmode:
                return
            return func(*args, **kwargs)
        return wrapper
