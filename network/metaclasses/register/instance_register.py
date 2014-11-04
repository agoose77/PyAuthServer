from itertools import chain

from .type_register import TypeRegister

from ...iterators import RenewableGenerator, take_single
from ...signals import SignalListener

__all__ = ['InstanceRegister', '_ManagedInstanceBase']


class _ManagedInstanceBase(SignalListener):
    """Private base class for managed instances

    Provides API for registered callbacks,
    individual registered functions and registered status
    """

    def __init__(self, instance_id=None, register_immediately=False, allow_random_key=False):
        # Generator used for finding IDs
        self.allow_random_key = allow_random_key

        # Initial value
        self.instance_id = instance_id

        # Run clean init function
        self.on_initialised()

        # Add to register queue
        self.register(instance_id, immediately=register_immediately)

    def on_initialised(self):
        pass

    def on_registered(self):
        pass

    def on_unregistered(self):
        pass

    def register(self, instance_id, immediately=False):
        """Mark the instance for registered on the next graph update

        :param instance_id: ID to register to
        :param immediately: Avoid graph update and immediately register
        """
        cls = self.__class__

        if instance_id is None:
            if not self.allow_random_key:
                raise ValueError("No key specified")

            instance_id = cls.get_next_id()

        self.instance_id = instance_id

        if immediately:
            cls._register_to_graph(self)

        else:
            cls._pending_registered.add(self)

    def deregister(self, immediately=False):
        """Mark the instance for unregistered on the next graph update

        :param register: Avoid graph update and immediately immediately
        """
        if immediately:
            self.__class__._unregister_from_graph(self)

        else:
            self.__class__._pending_unregistered.add(self)

    @property
    def registered(self):
        try:
            return self._instances[self.instance_id] is self

        except KeyError:
            return False

    def __bool__(self):
        return self.registered

    def __repr__(self):
        class_name = self.__class__.__name__

        if not self.registered:
            return "(Instance {})".format(class_name)

        else:
            return "(Instance {}: id={})".format(class_name, self.instance_id)


class InstanceRegister(TypeRegister):
    """Graph managing metaclass

    Provides high level interface for managing instance objects
    Supports ID conflict resolution and ID recycling

    Most methods could be implemented as classmethods on the implementee,
    however this metaclass prevents namespace cluttering
    """

    def __new__(meta, name, parents, cls_attrs):
        parents += (_ManagedInstanceBase,)

        cls = super().__new__(meta, name, parents, cls_attrs)

        if not hasattr(cls, "_instances"):
            cls._instances = {}
            cls._pending_registered = set()
            cls._pending_unregistered = set()
            cls._id_generator = RenewableGenerator(cls.iter_available_ids)

        return cls

    @property
    def total_instances(cls):
        return len(cls._instances) + len(cls._pending_registered)

    def _register_to_graph(cls, instance):
        """Internal graph method
        Registers an instance to the instance dict

        :param instance: instance to be registered
        """
        if instance.registered:
            return

        cls._instances[instance.instance_id] = instance
        instance.register_signals()

        try:
            instance.on_registered()

        except Exception as err:
            raise err

    def _unregister_from_graph(cls, instance):
        """Internal graph method
        Un-registers an instance from instance dict

        :param instance: instance to be unregistered
        """
        if not instance.instance_id in cls._instances:
            return

        cls._instances.pop(instance.instance_id)

        try:
            instance.on_unregistered()

        except Exception as err:
            print(err)

        finally:
            instance.unregister_signals()

    def clear_graph(cls):
        """Removes all internal registered instances"""
        cls.update_graph()

        while cls._instances:
            instance = take_single(cls._instances.values())
            instance.deregister(immediately=True)

    def get_next_id(cls):
        """Gets the next free ID

        :returns: first free ID
        """
        next_id = next(cls._id_generator)
        try:
            cls.get_from_graph(next_id, False)

        except LookupError:
            return next_id

        return cls.get_next_id()

    def get_id_iterable(cls):
        """Get iterable of all potential IDs

        :returns: range object wider than the current range of IDs in use
        """
        return range(cls.total_instances + 1)

    def iter_available_ids(cls):
        """Get iterator of available Instance IDs"""
        potential_ids = cls.get_id_iterable()
        current_ids = cls.get_all_graph_ids()
        free_ids = set(potential_ids).difference(current_ids)

        if not free_ids:
            raise IndexError("No free Instance IDs remaining")

        return iter(free_ids)

    def get_all_graph_ids(cls):
        """Find all managed instance IDs, registered or otherwise"""
        return (instance.instance_id for instance in cls.get_graph_instances(only_registered=False))

    def get_graph_instances(cls, only_registered=True):
        """Find all maanged instances.

        :param only_registered: only include registered instances
        """
        if only_registered:
            return cls._instances.values()

        return chain(cls._instances.values(), cls._pending_registered)

    def graph_has_instance(cls, instance_id):
        """Checks for instance ID in registered instances

        :param instance_id: ID of instance
        """
        return instance_id in cls._instances

    def get_from_graph(cls, instance_id, only_registered=True):
        """Find instance with a given ID.

        Optionally includes those pending registered

        :param only_registered: only search registered instances
        """
        try:
            return cls._instances[instance_id]

        except KeyError:
            # If we don't want the other values
            if only_registered:
                raise LookupError

            try:
                return next(i for i in cls._pending_registered if i.instance_id == instance_id)

            except StopIteration:
                raise LookupError

    def remove_from_graph(cls, instance_id):
        """Remove instance with a given ID from the graph.
        Prevent registered if pending.

        :param instance_id: ID of instance to remove
        """
        try:
            instance = cls.get_from_graph(instance_id, only_registered=False)
        except LookupError:
            return

        cls._unregister_from_graph(instance)

        if instance in cls._pending_unregistered:
            cls._pending_unregistered.remove(instance)

        return instance

    def update_graph(cls):
        """Update internal managed instances.

        Registers pending instances which requested registered.

        Un-registers managed instances which requested un-registered
        """
        if cls._pending_registered:
            get_instance = cls._pending_registered.pop
            register = cls._register_to_graph

            while cls._pending_registered:
                instance = get_instance()
                register(instance)

        if cls._pending_unregistered:
            get_instance = cls._pending_unregistered.pop
            unregister = cls._unregister_from_graph

            while cls._pending_unregistered:
                instance = get_instance()
                unregister(instance)

    def __bool__(cls):
        return bool(cls._instances)

    def __getitem__(cls, key):
        return cls.get_from_graph(key)

    def __iter__(cls):
        return iter(cls._instances.values())

    def __len__(cls):
        return len(cls._instances)
