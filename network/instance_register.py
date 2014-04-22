from itertools import chain

from .iterators import RenewableGenerator
from .signals import SignalListener
from .type_register import TypeRegister

__all__ = ['InstanceRegister', 'InstanceMixins']


class InstanceMixins(SignalListener):
    """Mixing class for managed instances

    Provides API for registration callbacks,
    individual registration functions and registered status"""

    def __init__(self, instance_id=None, register=False,
                 allow_random_key=False, **kwargs):
        super().__init__()

        # Generator used for finding IDs
        self.allow_random_key = allow_random_key

        # Run clean init function
        self.on_initialised()

        # Add to register queue
        self.request_registration(instance_id, register)

    def on_initialised(self):
        pass

    def on_registered(self):
        pass

    def on_unregistered(self):
        pass

    def request_unregistration(self, unregister=False):
        if not self.registered:
            return

        self.__class__._to_unregister.add(self)

        if unregister:
            self.__class__._unregister_from_graph(self)

    def request_registration(self, instance_id, register=False):
        if instance_id is None:
            assert self.allow_random_key, "No key specified"
            instance_id = self.__class__.get_next_id()

        self.instance_id = instance_id
        self.__class__._to_register.add(self)

        if register:
            self.__class__._register_to_graph(self)

    @property
    def registered(self):
        return self._instances.get(self.instance_id) is self

    def __bool__(self):
        return self.registered

    def __repr__(self):
        if not self.registered:
            return "(Instance {})".format(self.__class__.__name__)
        return "(Instance {}: id={})".format(self.__class__.__name__,
                                                    self.instance_id)


class InstanceRegister(TypeRegister):
    """Graph managing metaclass

    Provides high level interface for managing instance objects
    Supports ID conflict resolution and ID recycling

    Most methods could be implemented as classmethods on the implementee,
    however this metaclass prevents namespace cluttering"""

    def __new__(self, name, parents, cls_attrs):
        parents += (InstanceMixins,)
        cls = super().__new__(self, name, parents, cls_attrs)

        if not hasattr(cls, "_instances"):
            cls._instances = {}
            cls._pending_registration = set()
            cls._pending_unregistration = set()
            cls._id_generator = RenewableGenerator(cls.get_available_ids)

        return cls

    def get_next_id(cls): # @NoSelf
        """Gets the next free ID

        :returns: first free ID"""
        next_id = next(cls._id_generator)
        try:
            cls.get_from_graph(next_id, False)

        except LookupError:
            return next_id

        return cls.get_next_id()

    def get_id_iterable(cls): # @NoSelf
        """Get iterable of all potential IDs

        :returns: range(total_ids + 1)"""
        id_range = len(tuple(cls.get_entire_graph_ids()))
        return range(id_range + 1)

    def get_available_ids(cls): # @NoSelf
        """Filters existing IDs from potential IDs

        :returns: iter(free_ids)"""
        potential_ids = cls.get_id_iterable()
        current_ids = cls.get_entire_graph_ids()
        free_ids = set(potential_ids).difference(current_ids)

        if not free_ids:
            raise IndexError("No free Instance IDs remaining")

        return iter(free_ids)

    def get_entire_graph_ids(cls, instigator=None):  # @NoSelf
        registered_ids = (k for k, v in cls._instances.items()
                          if v != instigator)
        pending_ids = (i.instance_id for i in cls._pending_registration
                       if i != instigator)
        return chain(registered_ids, pending_ids)

    def get_graph_instances(cls, only_registered=True):  # @NoSelf
        """Find all registered instances
        Includes instances pending registration according to argument

        :param only_registered: only include registered instances"""
        if only_registered:
            return cls._instances.values()
        return chain(cls._instances.values(), cls._pending_registration)

    def graph_has_instance(cls, instance_id):  # @NoSelf
        """Checks for instance ID in registered instances

        :param instance_id: ID of instance"""
        return instance_id in cls._instances

    def get_from_graph(cls, instance_id, only_registered=True):  # @NoSelf
        """Find instance with a given ID
        optionally includes those pending registration

        :param only_registered: only search registered instances"""
        try:
            return cls._instances[instance_id]

        except KeyError:
            # If we don't want the other values
            if only_registered:
                raise LookupError

            try:
                return next(i for i in cls._pending_registration
                            if i.instance_id == instance_id)
            except StopIteration:
                raise LookupError

    def remove_from_entire_graph(cls, instance_id):  # @NoSelf
        """Remove instance with a given ID from the graph
        Prevents registration if pending

        :param instance_id: ID of instance to remove"""
        if not instance_id in cls._instances:
            return
        instance = cls._instances[instance_id]

        if not instance in cls._pending_unregistration:
            cls._pending_unregistration.add(instance)

        cls._unregister_from_graph(instance)

        for i in cls._pending_registration:
            if i.instance_id != instance_id:
                continue

            cls._pending_registration.remove(i)
            return i

    def update_graph(cls):  # @NoSelf
        """Update internal registered instances
        Removes and includes pending graph instances"""
        if cls._pending_registration:
            get_instance = cls._pending_registration.pop
            register = cls._register_to_graph
            while cls._pending_registration:
                register(get_instance())

        if cls._pending_unregistration:
            get_instance = cls._pending_unregistration.pop
            unregister = cls._unregister_from_graph
            while cls._pending_unregistration:
                unregister(get_instance())

    def clear_graph(cls):  # @NoSelf
        """Removes all internal registered instances"""
        cls.update_graph()

        get_instance = cls._instances.popitem
        while cls._instances:
            instance = get_instance()
            instance.request_unregistration(unregister=True)

    def _register_to_graph(cls, instance):  # @NoSelf
        """Internal graph method
        Registers an instance to the instance dict

        :param instance: instance to be registered"""
        if instance.registered:
            return

        cls._instances[instance.instance_id] = instance
        cls._pending_registration.remove(instance)

        try:
            instance.on_registered()
        except Exception as err:
            raise err

    def _unregister_from_graph(cls, instance):  # @NoSelf
        """Internal graph method
        Unregisters an instance from instance dict

        :param instance: instance to be unregistered"""
        cls._instances.pop(instance.instance_id)
        cls._pending_unregistration.remove(instance)

        try:
            instance.on_unregistered()

        except Exception:
            raise

        finally:
            instance.unregister_signals()

    def __getitem__(cls, key):  # @NoSelf
        return cls.get_from_graph(key)

    def __iter__(cls):  # @NoSelf
        return iter(cls._instances.values())

    def __len__(cls):  # @NoSelf
        return len(cls._instances)
