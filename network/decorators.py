from functools import wraps


def reliable(func):
    func.__annotations__['reliable'] = True
    return func


def simulated(func):
    func.__annotations__['simulated'] = True
    return func


def signal_listener(signal_type, global_listener):
    def wrapper(func):
        func.__annotations__['signal'] = signal_type
        func.__annotations__['context_dependant'] = not global_listener
        return func
    return wrapper


class run_on:
    '''Runs method in netmode specific scope only'''

    def __init__(self, netmode):
        self.netmode = netmode
        from .replicables import WorldInfo
        self._system_info = WorldInfo

    def __call__(self, func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if self._system_info.netmode != self.netmode:
                return
            return func(*args, **kwargs)
        return wrapper
