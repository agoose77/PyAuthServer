from inspect import isfunction

from .instance_register import InstanceRegister
from ..mapping.attribute_mapping import AttributeMeta
from ..mapping.rpc_mapping import RPCMeta
from ...conditions import is_annotatable
from ...descriptors import ContextMember
from ...decorators import get_annotation, requires_permission
from ...enums import Netmodes
from ...rpc import RPCInterfaceFactory


__all__ = ['ReplicableRegister']


class ReplicableRegister(AttributeMeta, RPCMeta, InstanceRegister):
    """Creates interfaces for RPCs and Attributes in Replicable class.

    Wraps methods in protectors for simulated decorators.
    """

    _forced_redefinitions = {}

    _of_type_cache = ContextMember({})
    _of_subclass_cache = ContextMember({})

    def __new__(metacls, cls_name, bases, cls_dict):
        # We need not operate on base classes
        if not bases:
            return super().__new__(metacls, cls_name, bases, cls_dict)

        # Some replicated functions might have marked parameters, they will be recreated per subclass type
        marked_parameter_functions = {}

        # Include certain RPCs for redefinition
        for parent_cls in set(bases).intersection(metacls._forced_redefinitions):
            rpc_functions = metacls._forced_redefinitions[parent_cls]

            for name, function in rpc_functions.items():
                # Only redefine inherited rpc calls
                if name in cls_dict:
                    continue

                # Redefine method as unwrapped function (before RPC wrapper)
                cls_dict[name] = function

        # Get all the member methods
        for name, value in cls_dict.items():
            # Only wrap valid members
            if not metacls.is_wrapable(value) or metacls.is_found_in_parents(name, bases):
                continue

            # Wrap function with permission wrapper
            value = requires_permission(value)

            # Automatically wrap RPC
            if metacls.is_unbound_rpc_function(value):
                value = RPCInterfaceFactory(value)

                # If subclasses will need copies (because of MarkedAttribute annotations)
                if value.has_marked_parameters:
                    marked_parameter_functions[name] = value.function

            cls_dict[name] = value

        cls = super().__new__(metacls, cls_name, bases, cls_dict)

        # If we will require redefinitions
        if marked_parameter_functions:
            metacls._forced_redefinitions[cls] = marked_parameter_functions

        return cls

    def subclass_of_type(cls, cls_type):
        """Find registered Replicable instances that are subclasses of a given type

        :param actor_type: type to compare against
        :returns: list of subclass instances
        """
        try:
            return cls._of_subclass_cache[cls_type]

        except KeyError:
            return set()

    def of_type(cls, cls_type):
        """Find Replicable instances with provided type

        :param cls_type: class type to find
        :returns: list of sibling instances derived from provided type
        """
        try:
            return cls._of_type_cache[cls_type]

        except KeyError:
            return set()

    @staticmethod
    def is_unbound_rpc_function(func):
        """Determine if function is annotated as an RPC call

        :param func: function to test
        """
        if not is_annotatable(func):
            return False

        return_type = get_annotation("return", default=None)(func)
        return return_type in Netmodes

    @staticmethod
    def is_wrapable(attribute):
        """Determine if function can be wrapped as an RPC call

        :param attribute: attribute in question
        """
        return isfunction(attribute) and not isinstance(attribute, (classmethod, staticmethod))

    @classmethod
    def is_found_in_parents(metacls, name, parents):
        """Determine if parent classes contain an attribute

        :param name: name of attribute
        :param parents: parent classes
        """
        for parent in parents:

            for cls in reversed(parent.__mro__):

                if hasattr(cls, name):
                    return True

                if cls.__class__ is metacls:
                    break

        return False
