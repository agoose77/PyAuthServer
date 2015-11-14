from collections import OrderedDict
from functools import update_wrapper
from inspect import signature, Parameter

from ..annotations.conditions import is_reliable
from ..annotations.decorators import get_annotation
from ..type_serialisers import FlagSerialiser, TypeInfo


class Pointer:
    """Pointer to member of object"""

    def __init__(self, qual_name):
        self._qualname = qual_name

    def __call__(self, cls):
        """Retrieve member from object

        :param cls: object to traverse
        """
        parts = self._qualname.split(".")

        try:
            obj = cls
            for part in parts:
                obj = getattr(obj, part)

        except AttributeError:
            raise AttributeError("Unable to resolve Pointer '{}' for '{}' class".format(self._qualname, cls.__name__))

        return obj


def _resolve_pointers(cls, type_info):
    data = {}

    for arg_name, arg_value in type_info.data.items():
        if isinstance(arg_value, TypeInfo):
            arg_value = _resolve_pointers(cls, arg_value)

        elif isinstance(arg_value, Pointer):
            arg_value = arg_value(cls)

        data[arg_name] = arg_value

    # Allow types to be marked
    data_type = type_info.data_type

    if isinstance(data_type, Pointer):
        data_type = type_info.data_type(cls)

    return TypeInfo(data_type, **data)


def resolve_pointers(cls, arguments):
    return OrderedDict(((name, _resolve_pointers(cls, value)) for name, value in arguments.items()))


def contains_pointer(arguments):
    for argument in arguments.values():
        if isinstance(argument, TypeInfo):
            if isinstance(argument.data_type, Pointer):
                return True

            if contains_pointer(argument.data):
                return True

        elif isinstance(argument, Pointer):
            return True

    return False


get_return_annotation = get_annotation("return")


def is_replicated_function(func):
    return get_return_annotation(func) is not None


class ReplicatedFunctionQueueDescriptor:

    def __init__(self):
        self._queues = {}

    def __get__(self, instance, owner):
        if instance is None:
            return self

        return self._queues[instance]

    def bind_instance(self, instance):
        self._queues[instance] = []

    def unbind_instance(self, instance):
        del self._queues[instance]


class ReplicatedFunctionsDescriptor:

    def __init__(self):
        self._descriptor_stores = {}

        self.function_descriptors = OrderedDict()

    def __get__(self, instance, owner):
        if instance is None:
            return self

        return self._descriptor_stores[instance]

    def extend(self, descriptor):
        function_descriptors = self.function_descriptors

        for name, function_descriptor in descriptor.function_descriptors.items():
            new_descriptor = function_descriptor.duplicate_for_child_class()

            function_descriptors[name] = new_descriptor

    def bind_instance(self, instance):
        cls = instance.__class__

        # Bind child descriptors
        descriptor_store = {}
        for descriptor in self.function_descriptors.values():
            descriptor.bind_instance(instance)
            descriptor_store[descriptor.index] = descriptor.__get__(instance, cls)

        self._descriptor_stores[instance] = descriptor_store

    def unbind_instance(self, instance):
        del self._descriptor_stores[instance]

        for descriptor in self.function_descriptors.values():
            descriptor.unbind_instance(instance)


class LocalReplicatedFunction:

    def __init__(self, function, deserialise):
        self.function = function
        self.deserialise = deserialise

        # Copy meta info
        update_wrapper(self, function)

    def __call__(self, *args, **kwargs):
        self.function(*args, **kwargs)

    def __repr__(self):
        return "<ReplicatedFunction '{}'>".format(self.function.__qualname__)


class ReplicatedFunctionDescriptor:

    def __init__(self, function, index):
        self.function = function
        self.index = index
        self._bound_instances = {}

        # Get RPC info (ignore self)
        func_signature = signature(function.__get__("some_cls"))

        self._arguments = self.get_arguments(func_signature)
        self._target_netmode = func_signature.return_annotation
        self._binder = func_signature.bind

        self._root_serialiser = None
        self._is_reliable = is_reliable(function)

        # Copy meta info
        self.__annotations__ = function.__annotations__
        self.__name__ = function.__name__
        self.__doc__ = function.__doc__

    def __get__(self, instance, cls):
        if instance is None:
            return self

        try:
            return self._bound_instances[instance]

        except KeyError:
            return self.function.__get__(instance, cls)

    def __repr__(self):
        return "<ReplicatedFunctionDescriptor '{}'>".format(self.function.__qualname__)

    def create_mapping_from_arguments(self, args, kwargs):
        return self._binder(*args, **kwargs).arguments

    def serialise(self, *args, **kwargs):
        arguments = self.create_mapping_from_arguments(args, kwargs)
        return self.index, self._is_reliable, self._root_serialiser.pack(arguments)

    def deserialise(self, data, offset=0):
        items, bytes_read = self._root_serialiser.unpack(data, offset=offset)
        arguments = dict(items)

        return arguments, bytes_read

    @staticmethod
    def get_arguments(signature):
        parameters = signature.parameters.values()
        empty_parameter = Parameter.empty

        arguments = OrderedDict()

        for parameter in parameters:
            annotation = parameter.annotation

            if annotation is empty_parameter:
                raise ValueError("Invalid parameter")

            if isinstance(annotation, TypeInfo):
                arg_info = annotation

            elif isinstance(annotation, tuple):
                data_type, data = annotation
                arg_info = TypeInfo(data_type, **data)

            else:
                arg_info = TypeInfo(annotation)

            arguments[parameter.name] = arg_info

        return arguments

    def duplicate_for_child_class(self):
        if not contains_pointer(self._arguments):
            return self

        return self.__class__(self.function, self.index)

    def resolve_pointers(self, cls):
        arguments = self._arguments

        if contains_pointer(arguments):
            arguments = resolve_pointers(cls, self._arguments)

        self._root_serialiser = FlagSerialiser(arguments)

    def bind_instance(self, instance):
        bound_function = self.function.__get__(instance)

        # Execute this locally
        if instance.scene.world.netmode == self._target_netmode:
            function = LocalReplicatedFunction(bound_function, self.deserialise)

        # Execute this remotely
        else:
            def function(*args, **kwargs):
                result = self.serialise(*args, **kwargs)
                instance.replicated_function_queue.append(result)

        self._bound_instances[instance] = function

    def unbind_instance(self, instance):
        self._bound_instances.pop(instance)
