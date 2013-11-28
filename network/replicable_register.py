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
        return "wrapped" in func.__annotations__

    def permission_wrapper(func):
        simulated_proxy = Roles.simulated_proxy
        func_is_simulated = is_simulated(func)

        @wraps(func)
        def func_wrapper(*args, **kwargs):

            try:
                assumed_instance = args[0]

            # Static method needs no permission
            except IndexError:
                return func(*args, **kwargs)

            else:
                # Check that the assumed instance/class has context_subscribers role method
                if hasattr(assumed_instance, "roles"):
                    arg_roles = assumed_instance.roles
                    # Check that the roles are of an instance
                    try:
                        local_role = arg_roles.local
                    except AttributeError:
                        return

                    # Permission checks
                    if (local_role > simulated_proxy or(func_is_simulated and
                                            local_role >= simulated_proxy)):
                        return func(*args, **kwargs)

                    elif getattr(assumed_instance, "verbose_execution", False):
                        print("Error executing '{}': \
                               Function does not have permission:\n{}".format(
                                              func.__qualname__, arg_roles))

                elif getattr(assumed_instance, "verbose_execution", False):
                    print("Error executing {}: \
                        Function does not have permission roles")

        func_wrapper.__annotations__['wrapped'] = True

        return func_wrapper
