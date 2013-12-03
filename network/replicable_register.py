from .conditions import is_simulated
from .enums import Roles, Netmodes
from .instance_register import InstanceRegister
from .rpc import RPC

from functools import wraps
from inspect import getmembers
from traceback import print_exc
from types import FunctionType


class ReplicableRegister(InstanceRegister):

    def __new__(meta, cls_name, bases, attrs):
        # If this isn't the base class
        if bases:
            # Get all the member methods
            for name, value in attrs.items():
                if meta.found_in_parents(name, bases):
                    continue

                # Wrap them with permission
                if not isinstance(value, (FunctionType, classmethod,
                                      staticmethod)):
                    continue

                if meta.is_wrapped(value):
                    continue

                # Recreate RPC from its function
                if isinstance(value, RPC):
                    print("Found pre-wrapped RPC call: {}, "\
                          "re-wrapping...(any data defined in "\
                          "__init__ will be lost)".format(name))
                    value = value._function

                value = meta.permission_wrapper(value)

                # Automatically wrap RPC
                if meta.is_rpc(value) and not isinstance(value, RPC):
                    value = RPC(value)

                attrs[name] = value

        return super().__new__(meta, cls_name, bases, attrs)

    def is_rpc(func):
        try:
            annotations = func.__annotations__
        except AttributeError:
            if not hasattr(func, "__func__"):
                return False
            annotations = func.__func__.__annotations__

        try:
            return_type = annotations['return']
        except KeyError:
            return False

        return return_type in Netmodes

    def found_in_parents(name, parents):
        for parent in parents:
            if name in dir(parent):
                return True

    def is_wrapped(func):
        return bool(func.__annotations__.get("wrapped"))

    def mark_wrapped(func):
        func.__annotations__['wrapped'] = True

    @classmethod
    def permission_wrapper(meta, func):
        simulated_proxy = Roles.simulated_proxy
        func_is_simulated = is_simulated(func)

        @wraps(func)
        def func_wrapper(*args, **kwargs):

            try:
                assumed_instance = args[0]

            # Static method needs no permission
            except IndexError:
                return func(*args, **kwargs)

            # Check that the assumed instance/class has roles
            try:
                arg_roles = assumed_instance.roles
            except AttributeError:
                return

            # Check that the roles are of an instance
            local_role = arg_roles.local

            # Permission checks
            if (local_role > simulated_proxy or(func_is_simulated and
                                    local_role >= simulated_proxy)):
                return func(*args, **kwargs)

        meta.mark_wrapped(func)

        return func_wrapper
