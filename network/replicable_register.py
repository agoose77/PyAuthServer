from .conditions import is_simulated
from .enums import Roles, Netmodes
from .instance_register import InstanceRegister
from .rpc import RPCInterfaceFactory

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

                # Wrap them with permission
                if not isinstance(value, (FunctionType, classmethod,
                                      staticmethod)):
                    continue

                if meta.should_ignore(name, value, bases):
                    continue

                # This is required to ensure class arguments
                # Are not overwritten by child instances
                if isinstance(value, RPCInterfaceFactory):
                    print("Found wrapped RPC call: {}, re-wrapping..."
                          .format(name))
                    # Take the function and move it up
                    value = value.function

                # RPC calls will have already wrapped their value
                else:
                    value = meta.permission_wrapper(value)

                # Automatically wrap RPC
                if meta.is_rpc(value):
                    value = RPCInterfaceFactory(value)

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

    @classmethod
    def found_in_parents(meta, name, parents):
        for parent in parents:
            for cls in reversed(parent.__mro__):
                if hasattr(cls, name):
                    return True
                if cls.__class__ == meta:
                    break
        return False

    @classmethod
    def should_ignore(meta, name, func, bases):
        return meta.is_wrapped(func) or meta.found_in_parents(name, bases)

    def mark_wrapped(func):
        func.__annotations__['wrapped'] = True

    def is_wrapped(func):
        return bool(func.__annotations__.get("wrapped"))

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
