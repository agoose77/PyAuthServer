from .annotations.decorators import requires_permission
from .enums import Roles
from .factory import ProtectedInstance, NamedSubclassTracker, restricted_method
from .replication import is_replicated_function, ReplicatedFunctionQueueDescriptor, ReplicatedFunctionDescriptor, \
    SerialisableDataStoreDescriptor, Serialisable

from collections import OrderedDict
from inspect import isfunction, getmembers


def enforce_call_roles(namespace):
    result = namespace.copy()

    for name, value in namespace.items():
        if isfunction(value):
            result[name] = requires_permission(value)

    return result


class ReplicableMetacls(NamedSubclassTracker):

    def __prepare__(name, bases):
        return OrderedDict()

    @classmethod
    def is_not_root(metacls, bases):
        for base_cls in bases:
            if isinstance(base_cls, metacls):
                return True

        return False

    def __new__(metacls, name, bases, namespace):
        function_index = 0

        replicated_functions = namespace['replicated_functions'] = {}
        serialisable_data = namespace['serialisable_data'] = SerialisableDataStoreDescriptor()

        namespace['replicated_function_queue'] = ReplicatedFunctionQueueDescriptor()

        # If this class is the root class, allow all methods to be called
        is_not_root = metacls.is_not_root(bases)

        for attr_name, value in namespace.items():
            if attr_name.startswith("__"):
                continue

            if isfunction(value):
                if is_replicated_function(value):
                    descriptor = ReplicatedFunctionDescriptor(value, function_index)
                    replicated_functions[function_index] = descriptor
                    function_index += 1

                    value = descriptor

                if is_not_root:
                    # Wrap function with permission wrapper
                    value = requires_permission(value)

                namespace[attr_name] = value

            # Only register new names (not required explicity, but safe)
            elif isinstance(value, Serialisable):
                value.name = attr_name

        cls = super().__new__(metacls, name, bases, namespace)

        # Register serialisables, including parent-class members
        for attr_name, value in getmembers(cls):
            if isinstance(value, Serialisable):
                serialisable_data.add_serialisable(value)

        return cls


class Replicable(ProtectedInstance, metaclass=ReplicableMetacls):
    roles = Serialisable(Roles(Roles.authority, Roles.none))

    def __init__(self, scene, unique_id, is_static=False):
        self._scene = scene
        self._unique_id = unique_id
        self._is_static = is_static

        self._bind_descriptors()

    def _bind_descriptors(self):
        """Bind instance to class descriptors for replication"""
        cls = self.__class__

        cls.replicated_function_queue.bind_instance(self)
        cls.serialisable_data.bind_instance(self)

        for descriptor in cls.replicated_functions.values():
            descriptor.bind_instance(self)

    def _unbind_descriptors(self):
        cls = self.__class__
        for descriptor in cls.replicated_functions.values():
            descriptor.unbind_instance(self)

        cls.replicated_function_queue.unbind_instance(self)
        cls.serialisable_data.unbind_instance(self)

    def can_replicate(self, is_owner, is_initial):
        if is_initial:
            yield "roles"

    @restricted_method
    def on_destroyed(self):
        self._unbind_descriptors()

    @restricted_method
    def change_unique_id(self, unique_id):
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

