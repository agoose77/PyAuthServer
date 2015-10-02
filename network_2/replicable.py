from .annotations.decorators import requires_permission
from .factory import ProtectedInstance, NamedSubclassTracker, protected_method
from .replication import is_replicated_function, ReplicatedFunctionQueue, ReplicatedFunctionDescriptor, \
    SerialisableData, Serialisable

from collections import OrderedDict
from inspect import isfunction


def enforce_call_roles(namespace):
    result = namespace.copy()

    for name, value in namespace.items():
        if isfunction(value):
            result[name] = requires_permission(value)

    return result


class ReplicableMetacls(NamedSubclassTracker):

    def __prepare__(name, bases):
        return OrderedDict()

    def __new__(metacls, name, bases, namespace):
        function_index = 0

        replicated_functions = namespace['replicated_functions'] = {}
        serialisables = namespace['serialisables'] = OrderedDict()

        serialisable_data = namespace['serialisable_data'] = SerialisableData()
        replicated_function_queue = namespace['replicated_function_queue'] = ReplicatedFunctionQueue()

        # TODO register attr names for notifier
        # TODO just use serialisable_data for dedicated_to_serialisable mapping (o

        for attr_name, value in namespace.items():
            if is_replicated_function(value):
                namespace[attr_name] = descriptor = ReplicatedFunctionDescriptor(value, function_index)
                replicated_functions[function_index] = descriptor
                function_index += 1

            if isinstance(value, Serialisable):
                serialisables[attr_name] = value

        return super().__new__(metacls, name, bases, namespace)


class Replicable(ProtectedInstance, metaclass=ReplicableMetacls):

    def __init__(self, scene, unique_id, is_static=False):
        self._scene = scene
        self._unique_id = unique_id
        self._is_static = is_static

        cls = self.__class__

        cls.replicated_function_queue.bind_instance(self)
        self.serialisable_data.bind_instance(self)

        for descriptor in cls.replicated_functions.values():
            descriptor.bind_instance(self)

    @protected_method
    def on_destroyed(self):
        cls = self.__class__
        for descriptor in cls.replicated_functions.values():
            descriptor.unbind_instance(self)

        cls.replicated_function_queue.unbind_instance(self)
        self.serialisable_data.unbind_instance(self)

    def change_unique_id(self, unique_id):
        if self.__class__._is_restricted:
            raise RuntimeError("Only internal scene can change unique id")

        self._unique_id = unique_id

    @property
    def unique_id(self):
        return self._unique_id

    @property
    def is_static(self):
        return self._is_static

    @property
    def scene(self):
        return self._scene

    def __repr__(self):
        return "<{}.{}::{} replicable>".format(self.scene, self.__class__.__name__, self.unique_id)

