from .type_register import TypeRegister

from ...context import GlobalDataContext, ContextMember
from ...iterators import RenewableGenerator
from ...signals import SignalListener

__all__ = ['InstanceRegister', '_ManagedInstanceBase']


class _ManagedInstanceBase(SignalListener):
    """Private base class for managed instances

    Provides API for registered callbacks,
    individual registered functions and registered status
    """

    def __init__(self, instance_id=None, allow_random_key=False):
        # Generator used for finding IDs
        self.allow_random_key = allow_random_key

        # Initial value
        self.instance_id = instance_id

        # Add to register queue
        self.register()

        # Run clean init function
        self.on_initialised()

    def on_initialised(self):
        pass

    def on_registered(self):
        self.register_signals()

    def on_deregistered(self):
        self.unregister_signals()

    def register(self):
        """Mark the instance for registered on the next graph update

        :param instance_id: ID to register to
        """
        # Check instance isn't registered to this ID already
        instance_id = self.instance_id

        cls = self.__class__
        instances = cls._instances

        # Choose random ID
        if instance_id is None:
            if not self.allow_random_key:
                raise ValueError("No key specified, random keys are not permitted")

            instance_id = cls._get_next_id()
            self.instance_id = instance_id

        elif instance_id in instances:
            conflicting_instance = instances[instance_id]

            # Check we're not re-registering
            if conflicting_instance is not self:
                self.resolve_id_conflict(instance_id, conflicting_instance)

            else:
                raise ValueError("Unable to register instance: already registered")

        instances[self.instance_id] = self
        self.on_registered()

    def deregister(self):
        """Mark the instance for unregistered on the next graph update

        :param register: Avoid graph update and immediately immediately
        """
        if not self.registered:
            return

        self.__class__._instances.pop(self.instance_id)
        self.on_deregistered()

    def resolve_id_conflict(self, instance_id, conflicting_instance):
        raise ValueError("Unable to register instance with this ID: ID already in use")

    @property
    def registered(self):
        try:
            return self.__class__._instances[self.instance_id] is self

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


class InstanceRegister(TypeRegister, GlobalDataContext):
    """Graph managing metaclass

    Provides high level interface for managing instance objects
    Supports ID conflict resolution and ID recycling

    Most methods could be implemented as classmethods on the implementee,
    however this metaclass prevents namespace cluttering
    """

    _instances = ContextMember({})

    _id_generator = ContextMember(None)
    _id_generator.factory = lambda cls: RenewableGenerator(cls.get_available_ids)

    def __new__(metacls, name, parents, attrs):
        parents += (_ManagedInstanceBase,)

        return super().__new__(metacls, name, parents, attrs)

    def _get_next_id(cls):
        """Gets the next free ID
-
        :returns: first free ID
        """
        next_id = next(cls._id_generator)

        if next_id in cls:
            return cls._get_next_id()

        return next_id

    def get_id_range(cls):
        """Get iterable of all potential IDs

        :returns: range object wider than the current range of IDs in use
        """
        return range(len(cls._instances) + 1)

    def get_available_ids(cls):
        """Get iterator of available Instance IDs"""
        potential_ids = cls.get_id_range()
        current_ids = cls._instances.keys()
        free_ids = set(potential_ids).difference(current_ids)

        if not free_ids:
            raise IndexError("No free Instance IDs remaining")

        return iter(free_ids)

    def clear_graph(cls):
        """Removes all internal registered instances"""
        instances = cls._instances
        while instances:
            instance_id, instance = instances.popitem()
            instance.deregister()

    def __contains__(cls, key):
        return key in cls._instances

    def __bool__(cls):
        return bool(cls._instances)

    def __getitem__(cls, key):
        return cls._instances[key]

    def __iter__(cls):
        return iter(cls._instances.values())

    def __len__(cls):
        return len(cls._instances)