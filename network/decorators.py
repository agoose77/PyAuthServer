from .rpc import RPCInterface

from functools import wraps, update_wrapper
from inspect import signature


def reliable(func):
    func.__annotations__['reliable'] = True
    return func


def simulated(func):
    func.__annotations__['simulated'] = True
    return func


def supply_data(**args):
    def wrapper(func):
        func.__annotations__['class_data'] = args
        return func
    return wrapper


def signal_listener(signal_type, global_listener):
    def wrapper(func):
        signals = func.__annotations__.setdefault('signals', [])
        signals.append((signal_type, not global_listener))
        return func
    return wrapper


def requires_netmode(netmode):
    from .replicables import WorldInfo

    def wrapper(func):
        @wraps(func)
        def _wrapper(*args, **kwargs):
            if WorldInfo.netmode != netmode:
                return

            return func(*args, **kwargs)

        return _wrapper

    return wrapper
