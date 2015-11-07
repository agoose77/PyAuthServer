from collections import OrderedDict
from inspect import isfunction

from .annotations.decorators import requires_permission
from .enums import Roles
from .factory import ProtectedInstance, NamedSubclassTracker, restricted_method
from .messages import MessagePasser
from .replication import is_replicated_function, ReplicatedFunctionQueueDescriptor, ReplicatedFunctionDescriptor, \
    ReplicatedFunctionsDescriptor, SerialisableDataStoreDescriptor, Serialisable


class ReplicableMetacls(NamedSubclassTracker):

    @classmethod
    def get_root(metacls, bases):
        for base_cls in reversed(bases):
            if isinstance(base_cls, metacls):
                return base_cls

    def __prepare__(name, bases):
        return OrderedDict()

    def __new__(metacls, name, bases, namespace):
        replicated_function_queue = namespace['replicated_function_queue'] = ReplicatedFunctionQueueDescriptor()
        replicated_functions = namespace['replicated_functions'] = ReplicatedFunctionsDescriptor()
        serialisable_data = namespace['serialisable_data'] = SerialisableDataStoreDescriptor()

        serialisables = serialisable_data.serialisables
        function_descriptors = replicated_functions.function_descriptors

        # Inherit from parent classes
        for cls in reversed(bases):
            if not isinstance(cls, ReplicableMetacls):
                continue

            serialisables.extend(cls.serialisable_data.serialisables)
            function_descriptors.extend(cls.replicated_functions.function_descriptors)

        # Check this is not the root class
        root = metacls.get_root(bases)
        function_index = len(function_descriptors)

        # Register serialisables, including parent-class members
        for attr_name, value in namespace.items():
            if attr_name.startswith("__"):
                continue

            # Add Serialisable to serialisables list
            if isinstance(value, Serialisable):
                value.name = attr_name
                serialisables.append(value)

            if isfunction(value):
                # Wrap function in ReplicatedFunctionDescriptor
                if is_replicated_function(value):
                    descriptor = ReplicatedFunctionDescriptor(value, function_index)
                    function_descriptors.append(descriptor)
                    value = descriptor

                # Wrap function with permission wrapper
                if root and not hasattr(root, attr_name):
                    value = requires_permission(value)

                namespace[attr_name] = value

        return super().__new__(metacls, name, bases, namespace)


class Replicable(ProtectedInstance, metaclass=ReplicableMetacls):
    roles = Serialisable(Roles(Roles.authority, Roles.none))

    # Temp data type
    owner = Serialisable(data_type="<Replicable>")
    torn_off = Serialisable(False, notify_on_replicated=True)

    replication_update_period = 1 / 30
    replication_priority = 1
    replicate_to_owner = True
    replicate_temporarily = False

    def __new__(cls, scene, unique_id, is_static=False):
        self = super().__new__(cls)

        self._scene = scene
        self._unique_id = unique_id
        self._is_static = is_static

        self.messenger = MessagePasser()

        self._bind_descriptors()

        return self

    def _bind_descriptors(self):
        """Bind instance to class descriptors for replication"""
        cls = self.__class__

        cls.replicated_function_queue.bind_instance(self)
        cls.serialisable_data.bind_instance(self)
        cls.replicated_functions.bind_instance(self)

    def _unbind_descriptors(self):
        cls = self.__class__

        cls.replicated_functions.unbind_instance(self)
        cls.replicated_function_queue.unbind_instance(self)
        cls.serialisable_data.unbind_instance(self)

    @property
    def root(self):
        replicable = self
        while replicable.owner:
            replicable = replicable.owner

        return replicable

    def can_replicate(self, is_owner, is_initial):
        if is_initial:
            yield "roles"

        yield "owner"
        yield "torn_off"

    def on_replicated(self, name):
        if name == "torn_off":
            if self.torn_off:
                self.roles.local = Roles.authority

    @restricted_method
    def on_destroyed(self):
        self._unbind_descriptors()

        self._scene = None
        self._unique_id = None
        self.messenger.clear_subscribers()

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


# Circular dependency
Replicable.owner.data_type = Replicable