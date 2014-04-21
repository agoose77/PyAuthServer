from .attribute_register import AttributeMeta
from .conditions import is_simulated
from .enums import Roles, Netmodes
from .instance_register import InstanceRegister
from .rpc import RPCInterfaceFactory
from .rpc_register import RPCMeta

from functools import wraps
from types import FunctionType

__all__ = ['ReplicableRegister']


class ReplicableRegister(AttributeMeta, RPCMeta, InstanceRegister):

    forced_redefinitions = {}

    def __new__(self, cls_name, bases, cls_dict):
        # If this isn't the base class
        unshareable_rpc_functions = {}

        # We cannot operate on base classes
        if not bases:
            return super().__new__(self, cls_name, bases, cls_dict)

        # Include certain RPCs for redefinition
        for parent_cls in bases:
            if not parent_cls in self.forced_redefinitions:
                continue

            rpc_functions = self.forced_redefinitions[parent_cls]
            for name, function in rpc_functions.items():
                if name in cls_dict:
                    continue

                cls_dict[name] = function

        # Get all the member methods
        for name, value in cls_dict.items():
            if (not self.is_wrappable(value) or
                self.found_in_parents(name, bases)):
                continue

            # Wrap function with permission wrapper
            value = self.permission_wrapper(value)

            # Automatically wrap RPC
            if self.is_unbound_rpc_function(value):
                value = RPCInterfaceFactory(value)

                # If subclasses will need copies
                if value.has_marked_parameters:
                    unshareable_rpc_functions[name] = value.original_function

            cls_dict[name] = value

        cls = super().__new__(self, cls_name, bases, cls_dict)

        # If we will require redefinitions
        if unshareable_rpc_functions:
            self.forced_redefinitions[cls] = unshareable_rpc_functions

        return cls

    def is_unbound_rpc_function(func):  # @NoSelf
        try:
            annotations = func.__annotations__

        except AttributeError:
            return False

        try:
            return_type = annotations['return']

        except KeyError:
            return False

        return return_type in Netmodes

    @classmethod
    def is_wrappable(cls, value):
        return (isinstance(value, FunctionType) and not
                isinstance(value, (classmethod, staticmethod)))

    @classmethod
    def found_in_parents(meta, name, parents):
        for parent in parents:
            for cls in reversed(parent.__mro__):
                if hasattr(cls, name):
                    return True

                if cls.__class__ == meta:
                    break

        return False

    def mark_wrapped(func):  # @NoSelf
        func.__annotations__['wrapped'] = True

    def is_wrapped(func):  # @NoSelf
        return bool(func.__annotations__.get("wrapped"))

    @classmethod
    def permission_wrapper(meta, func):
        simulated_proxy = Roles.simulated_proxy  # @UndefinedVariable
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
