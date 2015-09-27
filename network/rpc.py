from .flag_serialiser import FlagSerialiser
from .type_flag import TypeFlag
from .logger import logger

from collections import OrderedDict
from copy import deepcopy
from functools import update_wrapper
from inspect import signature, Parameter

__all__ = ['RPCInterfaceFactory', 'RPCInterface', 'Pointer']


def _resolve_parameters(cls, flag):
    data = flag.data

    for arg_name, arg_value in data.items():
        if isinstance(arg_value, TypeFlag):
            _resolve_parameters(cls, arg_value)

        if not isinstance(arg_value, Pointer):
            continue

        data[arg_name] = arg_value(cls)

    # Allow types to be marked
    if isinstance(flag.data_type, Pointer):
        flag.data_type = flag.data_type(cls)


class Pointer:
    """Pointer to member of object"""

    def __init__(self, qualname):
        self._qualname = qualname

    def __call__(self, obj):
        """Retrieve member from object

        :param obj: object to traverse
        """
        parts = self._qualname.split(".")

        for part in parts:
            obj = getattr(obj, part)

        return obj


class RPCInterface:
    """Mediates RPC calls to/from peers"""

    def __init__(self, function, serialiser_info):
        # Used to isolate rpc_for_instance for each function for each instance
        self._function_call = function.__call__
        self._function_name = function.__qualname__
        self._function_signature = signature(function)

        # Information about RPC
        update_wrapper(self, function)

        # Get the function signature
        self.target = self._function_signature.return_annotation

        # Interface between data and bytes
        self._binder = self._function_signature.bind

        try:
            self._serialiser = FlagSerialiser(serialiser_info)

        except TypeError:
            logger.exception("Unable to create serialiser for RPC call: {}".format(self._function_name))

        # Get current world
        from .world import get_current_netmode
        self._netmode = get_current_netmode()

    def __call__(self, *args, **kwargs):
        # Determines if call should be executed or bounced
        if self.target == self._netmode:
            return self._function_call(*args, **kwargs)

        # Store serialised argument data for later sending
        arguments = self._binder(*args, **kwargs).arguments

        try:
            packed_data = self._serialiser.pack(arguments)
            self._interface.set(packed_data)

        except Exception:
            logger.exception("Could not package RPC call: '{}'".format(self._function_name))

    def __repr__(self):
        return "<RPC Interface {}>".format(self._function_name)

    def execute(self, bytes_string):
        """Execute RPC from bytes_string
        :param bytes_string: Byte stream of RPC call data
        """
        # Unpack RPC
        try:
            unpacked_data, unpacked_size = self._serialiser.unpack(bytes_string)
            self._function_call(**dict(unpacked_data))

        except Exception:
            logger.exception("Could not invoke RPC call: '{}'".format(self._function_name))

        return unpacked_size

    def register(self, interface, rpc_id):
        """Register individual RPC interface for a class Instance

        :param interface: interface to write rpc calls to
        :param rpc_id: rpc call ID
        """
        self.rpc_id = rpc_id
        self._interface = interface


class RPCInterfaceFactory:
    """Manages instances of an RPC function for each object"""

    def __init__(self, function):
        update_wrapper(self, function)

        self._by_instance = {}
        self._ordered_parameters = self.order_arguments(signature(function))
        self._serialiser_parameters = None

        self.validate_function_definition(self._ordered_parameters, function)

        self.function = function
        self.has_marked_parameters = self.has_pointers(self._ordered_parameters)

    def __get__(self, instance, base):
        """Return the registered RPCInterface for the current class instance.

        If there is no RPCInterface for the current class instance, return the raw function, this may occur when
        the RPCInterfaceFactory descriptor is overridden in a subclass

        :param instance: class instance which hosts the rpc call
        :param base: base type of class which hosts the rpc call
        """
        if instance is None:
            return self

        try:
            return self._by_instance[instance]

        # Allow subclasses to call superclass methods without invocation
        except KeyError:
            return self.function.__get__(instance)

    def __repr__(self):
        return "<RPC Factory {}>".format(self.function.__qualname__)

    @staticmethod
    def has_pointers(ordered_parameters):
        """Check for any Pointer instances in parameter data

        :param ordered_parameters: OrderedDict of function call parameters
        """
        lookup_type = Pointer

        for argument in ordered_parameters.values():
            if isinstance(argument.data_type, lookup_type):
                return True

            for arg_value in argument.data.values():
                if isinstance(arg_value, lookup_type):
                    return True

        return False

    def create_rpc_interface(self, instance):
        """Create a new RPC interface for a class instance.

        :param instance: class instance which defines the replicated function call
        """
        bound_function = self.function.__get__(instance)

        # Lazy load Create information for the serialiser
        if self._serialiser_parameters is None:
            self._serialiser_parameters = self.get_serialiser_parameters_for(instance.__class__)

        self._by_instance[instance] = interface = RPCInterface(bound_function, self._serialiser_parameters)

        return interface

    def get_serialiser_parameters_for(self, cls):
        """Return an OrderedDict of function parameters, replace any MarkedAttribute instances with current class
        attribute values.

        :param cls: class reference
        """
        serialiser_info = deepcopy(self._ordered_parameters)

        # Update with new values
        for argument in serialiser_info.values():
            _resolve_parameters(cls, argument)

        return serialiser_info

    @staticmethod
    def order_arguments(function_signature):
        """Order the parameters to the given function

        :param function_signature: function signature
        """
        parameter_values = function_signature.parameters.values()
        empty_parameter = Parameter.empty

        return OrderedDict((value.name, None if value.annotation is empty_parameter else value.annotation) for value
                           in parameter_values if isinstance(value.annotation, TypeFlag))

    @staticmethod
    def validate_function_definition(arguments, function):
        """Validate the format of an RPC function, to ensure that all arguments have provided type annotations.

        :param arguments: dictionary of function arguments
        :param function: function to validate
        """
        # Read all arguments
        function_name = function.__qualname__
        for parameter_name, parameter in arguments.items():
            if parameter is None:
                logger.error("RPC call '{}' has not provided a type annotation for parameter '{}'"
                             .format(function_name, parameter_name))
