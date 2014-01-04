from .handler_interfaces import static_description
from .descriptors import Attribute
from .rpc import RPCInterfaceFactory

from functools import partial
from collections import OrderedDict, deque
from inspect import getmembers

__all__ = ['ValueProperty', 'StorageInterface', 'RPCStorageInterface',
           'AttributeStorageInterface', 'AbstractStorageContainer',
           'RPCStorageContainer', 'AttributeStorageContainer']


class ValueProperty:
    """Property wrapper about data item
    Handles __get__ and __set__ calls by
    callbacks on the host class
    @requires: Host methods get_value(), set_value(arg)"""

    __slots__ = []

    def __get__(self, instance, base):
        if instance is None:
            return self
        return instance.get_value()

    def __set__(self, instance, value):
        instance.set_value(value)


class StorageInterface:
    """Interface for reading and writing a data value
    @var value: Property descriptor with settable and gettable value"""
    __slots__ = ["get_value", "set_value"]

    def __init__(self, getter, setter):
        self.get_value = getter
        self.set_value = setter

    value = ValueProperty()


class RPCStorageInterface(StorageInterface):
    """RPC storage interface
    Proxy for data storage only"""
    __slots__ = StorageInterface.__slots__

    def __init__(self, setter):
        super().__init__(None, setter)


class AttributeStorageInterface(StorageInterface):
    """Attribute storage interface
    Proxy for data storage, access and complaint status"""
    __slots__ = StorageInterface.__slots__ + ["set_complaint"]

    def __init__(self, getter, setter, complaint):
        super().__init__(getter, setter)

        self.set_complaint = complaint


class AbstractStorageContainer:
    """Abstract base class for reading and writing data values
    belonging an object"""

    def __init__(self, instance):
        self._mapping = self.get_member_instances(instance)
        self._ordered_mapping = self.get_ordered_members()

        self._lazy_name_mapping = {}
        self._storage_interfaces = {}
        self._instance = instance

        self.data = self.get_default_data()

    def get_default_value(self, member):
        raise NotImplementedError

    def check_is_supported(self, member):
        raise NotImplementedError

    def get_member_instances(self, instance):
        is_supported = self.check_is_supported

        return {name: value for name, value in getmembers(instance.__class__)
                if is_supported(value)}

    def get_default_data(self):
        initial_data = self.get_default_value
        mapping = self._mapping
        return {member: initial_data(member) for member in mapping.values()}

    def get_ordered_members(self):
        mapping = self._mapping
        return OrderedDict((key, mapping[key]) for key in sorted(mapping))

    def get_member_by_name(self, name):
        return self._mapping[name]

    def get_name_by_member(self, member):
        try:
            return self._lazy_name_mapping[member]

        except KeyError:
            name = self._lazy_name_mapping[member] = next(n for n, a in
                                          self._mapping.items() if a == member)
            return name

    def register_storage_interfaces(self):
        new_interface = self.new_storage_interface
        store_interface = self._storage_interfaces.__setitem__

        for name, member in sorted(self._mapping.items()):
            store_interface(member, new_interface(name, member))

    def new_storage_interface(self, name, member):
        return StorageInterface(*self.get_storage_accessors(member))

    def get_storage_accessors(self, member):
        getter = partial(self.data.__getitem__, member)
        setter = partial(self.data.__setitem__, member)

        return getter, setter

    def get_storage_interface(self, member):
        return self._storage_interfaces[member]


class RPCStorageContainer(AbstractStorageContainer):
    """Storage container for RPC calls
    Handles stored data only"""
    def __init__(self, instance):
        super().__init__(instance)

        self.functions = []

    def check_is_supported(self, member):
        return isinstance(member, RPCInterfaceFactory)

    def get_default_data(self):
        return deque()

    def _add_call(self, member, value):
        self.data.append((member, value))

    def store_rpc(self, func):
        self.functions.append(func)
        return self.functions.index(func)

    def interface_register(self, instance):
        return partial(self._add_call, instance)

    def new_storage_interface(self, name, member):
        rpc_instance = member.create_rpc_interface(self._instance)
        rpc_id = self.store_rpc(rpc_instance)

        adder_func = partial(self._add_call, rpc_instance)

        interface = RPCStorageInterface(adder_func)
        rpc_instance.register(interface, rpc_id)

        return interface


class AttributeStorageContainer(AbstractStorageContainer):
    """Storage container for Attributes
    Handles data storage, access and complaints"""

    def __init__(self, instance):
        super().__init__(instance)

        self.complaints = self.get_default_complaints()

    @staticmethod
    def get_descriptions_of(data, static_description=static_description):
        return {attribute: static_description(value)
                for attribute, value in data.items()}

    def get_description_tuple(self, static_description=static_description):
        complaints = self.complaints
        data = self.data
        members = self._ordered_mapping.values()

        return tuple(complaints[member] if member in complaints else
                     static_description(data[member]) for member in members)

    def get_default_descriptions(self):
        return self.get_descriptions_of(self.get_default_data())

    def get_default_complaints(self):
        default_descriptions = self.get_default_descriptions()
        return {a: v for a, v in default_descriptions.items() if a.complain}

    def check_is_supported(self, member):
        return isinstance(member, Attribute)

    def get_default_value(self, attribute):
        return attribute.get_new_value()

    def new_storage_interface(self, name, member):
        getter, setter = self.get_storage_accessors(member)

        complain_setter = partial(self.complaints.__setitem__, member)
        interface = AttributeStorageInterface(getter, setter, complain_setter)
        default_value = self.get_default_value(member)

        member.register(self._instance, interface)
        setter(default_value)
        member.name = name

        return member
