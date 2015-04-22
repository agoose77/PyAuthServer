from .descriptors import Attribute
from .handlers import static_description
from .rpc import RPCInterfaceFactory

from collections import OrderedDict, deque, namedtuple
from functools import partial
from inspect import getmembers

__all__ = ['StorageInterface', 'RPCStorageInterface', 'AttributeStorageInterface', 'AbstractStorageContainer',
           'RPCStorageContainer', 'AttributeStorageContainer']


AttributeStorageInterface = namedtuple("StorageInterface", "get set complain")
RPCStorageInterface = namedtuple("StorageInterface", "set")
StorageInterface = namedtuple("StorageInterface", "get set")


class AbstractStorageContainer:
    """Abstract base class for reading and writing data values belonging an object"""

    def __init__(self, instance, mapping=None, ordered_mapping=None):
        self._lazy_name_mapping = {}
        self._storage_interfaces = {}
        self._instance = instance

        if mapping is None:
            self._mapping = self.get_member_instances(instance.__class__)

        else:
            self._mapping = mapping

        if ordered_mapping is None:
            self._ordered_mapping = self.get_ordered_members(self._mapping)

        else:
            self._ordered_mapping = ordered_mapping

        self.data = self.get_default_data()

    @classmethod
    def check_is_supported(cls, member):
        raise NotImplementedError()

    def get_default_data(self):
        initial_data = self.get_default_value
        mapping = self._mapping

        return {member: initial_data(member) for member in mapping.values()}

    def get_default_value(self, member):
        raise NotImplementedError()

    def get_member_by_name(self, name):
        return self._mapping[name]

    def get_name_by_member(self, member):
        try:
            return self._lazy_name_mapping[member]

        except KeyError:
            name = self._lazy_name_mapping[member] = next(n for n, a in self._mapping.items() if a is member)
            return name

    @classmethod
    def get_member_instances(cls, instance_cls):
        is_supported = cls.check_is_supported

        return {name: value for name, value in getmembers(instance_cls, is_supported)}

    def get_storage_accessors(self, member):
        getter = partial(self.data.__getitem__, member)
        setter = partial(self.data.__setitem__, member)

        return getter, setter

    def get_storage_interface(self, member):
        return self._storage_interfaces[member]

    @staticmethod
    def get_ordered_members(mapping):
        return OrderedDict((key, mapping[key]) for key in sorted(mapping))

    def new_storage_interface(self, name, member):
        return StorageInterface(*self.get_storage_accessors(member))

    def register_storage_interfaces(self):
        new_interface = self.new_storage_interface
        store_interface = self._storage_interfaces.__setitem__

        for name, member in self._ordered_mapping.items():
            store_interface(member, new_interface(name, member))


class RPCStorageContainer(AbstractStorageContainer):
    """Storage container for RPC calls.

    Handles stored data only.
    """

    def __init__(self, instance, *args, **kwargs):
        super().__init__(instance, *args, **kwargs)

        self.functions = []

    @classmethod
    def check_is_supported(cls, member):
        """Return True if class member is an instance of :py:class:`RPCInterfaceFactory`

        :param member: class member object
        """
        return isinstance(member, RPCInterfaceFactory)

    def _queue_function_call(self, member, value):
        """Add RPC call data to outgoing queue (internal).

        :param member: class member function
        :param value: rpc call data
        """
        self.data.append((member, value))

    def get_default_data(self):
        return deque()

    def new_storage_interface(self, name, member):
        """Return RPCStorageInterface instance for class member function.

        :param name: name of function
        :param member: member function
        """
        rpc_instance = member.create_rpc_interface(self._instance)
        self.functions.append(rpc_instance)
        rpc_id = len(self.functions) - 1

        queue_func = partial(self._queue_function_call, rpc_instance)

        interface = RPCStorageInterface(queue_func)
        rpc_instance.register(interface, rpc_id)

        return interface


class AttributeStorageContainer(AbstractStorageContainer):
    """Storage container for Attributes.

    Handles data storage, access and complaints.
    """

    def __init__(self, instance, *args, **kwargs):
        super().__init__(instance, *args, **kwargs)

        self.complaints = self.get_default_complaints()

    def get_description_mapping(self):
        """Return mapping of attributes to value network descriptions (:py:func:`network.handlers.static_description`)"""
        return {attribute: static_description(value) for attribute, value in self.data.items()}

    def get_ordered_descriptions(self):
        """Return ordered list of description values for member attributes

        Use cached complaint descriptions when present
        """
        complaints = self.complaints
        data = self.data
        members = self._ordered_mapping.values()
        get_description = static_description

        descriptions = [complaints[member] if member in complaints else get_description(data[member])
                        for member in members]
        return tuple(descriptions)

    def get_default_descriptions(self):
        return {attribute: static_description(attribute.initial_value) for attribute in self.data}

    def get_default_complaints(self):
        return {a: v for a, v in self.get_default_descriptions().items() if a.complain}

    @classmethod
    def check_is_supported(cls, member):
        """Return True if class member is an instance of :py:class:`network.descriptors.Attribute`

        :param member: class member object
        """
        return isinstance(member, Attribute)

    def get_default_value(self, attribute):
        """Return deepcopy of default value for attribute"""
        return attribute.get_new_value()

    def new_storage_interface(self, name, member):
        """Return new AttributeStorageInterface instance for class member

        :param name: name of attribute
        :param member: Attribute instance
        """
        getter, setter = self.get_storage_accessors(member)

        complain_setter = partial(self.complaints.__setitem__, member)
        interface = AttributeStorageInterface(getter, setter, complain_setter)
        default_value = self.get_default_value(member)

        member.register(self._instance, interface)
        setter(default_value)
        member.name = name

        return interface
