from .rpc import RPCInterface

from functools import wraps
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
        func.__annotations__['signal'] = signal_type
        func.__annotations__['context_dependant'] = not global_listener
        return func
    return wrapper


class SupplyData:

    def __init__(self, **keys):
        self._keys = keys

    def __call__(self, function):
        keys = self._keys

        function_signature = signature(function)
        function_arguments = RPCInterface.order_arguments(function_signature)
        requested_arguments = {name: function_arguments[name] for name in keys}

        @wraps(function)
        def wrapper(instance, *args, **kwargs):
            get_func = instance.__getattribute__

            for name, argument in requested_arguments.items():
                data = argument.data
                for key in keys[name]:
                    data[key] = get_func(key)

            return function(instance, *args, **kwargs)
        return wrapper


class RequireNetmode:
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
