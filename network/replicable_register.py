from .attribute_register import AttributeMeta
from .conditions import is_annotatable
from .decorators import get_annotation, requires_permission
from .enums import Roles, Netmodes
from .instance_register import InstanceRegister
from .rpc import RPCInterfaceFactory
from .rpc_register import RPCMeta

from inspect import isfunction

__all__ = ['ReplicableRegister']


class ReplicableRegister(AttributeMeta, RPCMeta, InstanceRegister):
    """Creates interfaces for RPCs and Attributes in Replicable class
    Wraps methods in protectors for simulated decorators"""     

    forced_redefinitions = {}

    def __new__(meta, cls_name, bases, cls_dict):
        # We cannot operate on base classes
        if not bases:
            return super().__new__(meta, cls_name, bases, cls_dict)

        # Some replicated functions might have marked parameters, they will be recreated per subclass type
        marked_parameter_functions = {}

        # Include certain RPCs for redefinition
        for parent_cls in set(bases).intersection(meta.forced_redefinitions):
            rpc_functions = meta.forced_redefinitions[parent_cls]

            for name, function in rpc_functions.items():
                # Only redefine inherited rpc calls
                if name in cls_dict:
                    continue

                # Redefine method as unwrapped function (before RPC wrapper)
                cls_dict[name] = function

        # Get all the member methods
        for name, value in cls_dict.items():
            # Only wrap valid members
            if not meta.is_wrappable(value) or meta.is_found_in_parents(name, bases):
                continue

            # Wrap function with permission wrapper
            value = requires_permission(value)

            # Automatically wrap RPC
            if meta.is_unbound_rpc_function(value):
                value = RPCInterfaceFactory(value)

                # If subclasses will need copies (because of MarkedAttribute annotations)
                if value.has_marked_parameters:
                    marked_parameter_functions[name] = value.function

            cls_dict[name] = value

        cls = super().__new__(meta, cls_name, bases, cls_dict)

        # If we will require redefinitions
        if marked_parameter_functions:
            meta.forced_redefinitions[cls] = marked_parameter_functions

        return cls

    @staticmethod
    def is_unbound_rpc_function(func):
        """Determine if function is annotated as an RPC call

        :param func: function to test
        """
        if not is_annotatable(func):
            return False

        return_type = get_annotation("return", default=None)(func)
        return return_type in Netmodes

    @classmethod
    def is_wrappable(mcs, attribute):
        """Determine if function can be wrapped as an RPC call

        :param attribute: attribute in question
        """
        return isfunction(attribute) and not isinstance(attribute, (classmethod, staticmethod))

    @classmethod
    def is_found_in_parents(mcs, name, parents):
        """Determine if parent classes contain an attribute

        :param name: name of attribute
        :param parents: parent classes
        """
        for parent in parents:

            for cls in reversed(parent.__mro__):

                if hasattr(cls, name):
                    return True

                if cls.__class__ is mcs:
                    break

        return False
