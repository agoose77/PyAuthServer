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

    def __call__(self, obj):
        """Retrieve member from object

        :param obj: object to traverse
        """
        parts = self._qualname.split(".")

        for part in parts:
            obj = getattr(obj, part)

        return obj


def _resolve_pointers(cls, flag):
    data = flag.data

    for arg_name, arg_value in data.items():
        if isinstance(arg_value, TypeInfo):
            _resolve_pointers(cls, arg_value)

        if not isinstance(arg_value, Pointer):
            continue

        data[arg_name] = arg_value(cls)

    # Allow types to be marked
    if isinstance(flag.data_type, Pointer):
        flag.data_type = flag.data_type(cls)


def resolve_pointers(cls, arguments):
    return OrderedDict(((name, _resolve_pointers(cls, value)) for name, value in arguments.items()))


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

        self.function_descriptors = []

    def __get__(self, instance, owner):
        if instance is None:
            return self

        return self._descriptor_stores[instance]

    def bind_instance(self, instance):
        cls = instance.__class__

        # Bind child descriptors
        descriptor_store = {}
        for descriptor in self.function_descriptors:
            descriptor.bind_instance(instance)
            descriptor_store[descriptor.index] = descriptor.__get__(instance, cls)

        self._descriptor_stores[instance] = descriptor_store

    def unbind_instance(self, instance):
        del self._descriptor_stores[instance]

        for descriptor in self.function_descriptors:
            descriptor.unbind_instance(instance)


class ReplicatedFunctionBase:

    def __init__(self, function, index, serialiser):
        self.index = index
        self.function = function
        self._serialiser = serialiser

        # Copy meta info
        update_wrapper(self, function)

    def __repr__(self):
        return "<ReplicatedFunction '{}'>".format(self.function.__qualname__)


class ReplicatedFunctionDeserialiser(ReplicatedFunctionBase):

    def __call__(self, *args, **kwargs):
        return self.function(*args, **kwargs)

    def deserialise(self, data, offset=0):
        items, bytes_read = self._serialiser.unpack(data, offset=offset)
        arguments = dict(items)

        return arguments, bytes_read


class ReplicatedFunctionSerialiser(ReplicatedFunctionBase):

    def __init__(self, function, index, serialiser, bind):
        super().__init__(function, index, serialiser)

        self._bind = bind
        self._is_reliable = is_reliable(function)

    def on_serialised(self, data):
        pass

    def serialise(self, *args, **kwargs):
        arguments = self._bind(args, kwargs)
        data = self.index, self._is_reliable, self._serialiser.pack(arguments)
        self.on_serialised(data)

    __call__ = serialise


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

        if self.check_has_pointers(self._arguments):
            self._root_serialiser = None

        else:
            self._root_serialiser = FlagSerialiser(self._arguments)

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

    @staticmethod
    def get_arguments(signature):
        parameters = signature.parameters.values()
        empty_parameter = Parameter.empty

        arguments = OrderedDict()

        for parameter in parameters:
            annotation = parameter.annotation

            if annotation is empty_parameter:
                raise ValueError("Invalid parameter")

            if isinstance(annotation, tuple):
                data_type, data = annotation

            else:
                data_type = annotation
                data = {}

            arguments[parameter.name] = TypeInfo(data_type, **data)

        return arguments

    @staticmethod
    def check_has_pointers(arguments):
        lookup_type = Pointer

        for argument in arguments.values():
            if isinstance(argument.data_type, lookup_type):
                return True

            for arg_value in argument.data.values():
                if isinstance(arg_value, lookup_type):
                    return True

        return False

    def bind_instance(self, instance):
        if self._root_serialiser is None:
            arguments = resolve_pointers(instance.__class__, self._arguments)
            serialiser = FlagSerialiser(arguments)

        else:
            serialiser = self._root_serialiser

        function = self.function.__get__(instance)

        # Execute this locally
        if instance.scene.world.netmode == self._target_netmode:
            replicated_function = ReplicatedFunctionDeserialiser(function, self.index, serialiser)

        # Execute this remotely
        else:
            replicated_function = ReplicatedFunctionSerialiser(function, self.index, serialiser,
                                                               self.create_mapping_from_arguments)
            replicated_function.on_serialised = instance.replicated_function_queue.append

        self._bound_instances[instance] = replicated_function

    def unbind_instance(self, instance):
        self._bound_instances.pop(instance)