from collections import defaultdict

from .descriptors import Attribute
from .enums import Roles
from .metaclasses.register import ReplicableRegister
from .signals import (ReplicableRegisteredSignal, ReplicableUnregisteredSignal)


__all__ = ['Replicable']


class Replicable(metaclass=ReplicableRegister):

    """Base class for all network involved objects
    Supports Replicated Function calls, Attribute replication
    and Signal subscription"""

    _MAXIMUM_REPLICABLES = 255
    _by_types = defaultdict(list)

    roles = Attribute(Roles(Roles.authority, Roles.none), notify=True)
    owner = Attribute(complain=True, notify=True)
    torn_off = Attribute(False, complain=True, notify=True)

    # Dictionary of class-owned instances
    subclasses = {}

    def __init__(self, instance_id=None, register_immediately=False, static=True, **kwargs):
        # If this is a locally authoritative
        self._local_authority = False

        # If this is a static mapping (requires static flag and a matchable ID)
        self._static = static and instance_id is not None

        # Setup the attribute storage
        self._attribute_container.register_storage_interfaces()
        self._rpc_container.register_storage_interfaces()

        self.owner = None

        # Replication properties
        self.relevant_to_owner = True
        self.always_relevant = False

        self.replicate_temporarily = False
        self.replication_priority = 1.0
        self.replication_update_period = 1 / 20

        # Instantiate parent (this is when the creation callback may be called)
        super().__init__(instance_id=instance_id, register_immediately=register_immediately,
                         allow_random_key=True, **kwargs)

    @property
    def is_static(self):
        return self._static

    @property
    def uppermost(self):
        """Walks the successive owner of each Replicable to find highest parent

        :returns: uppermost parent
        :rtype: :py:class:`network.replicable.Replicable` or :py:class:`None`
        """
        last = None
        replicable = self

        # Walk the parent tree until no parent
        try:
            while replicable:
                last, replicable = replicable, replicable.owner

        except AttributeError:
            pass

        return last

    @classmethod
    def create_or_return(cls, instance_id, register_immediately=True):
        """Creates a replicable if it is not already registered.

        Called by the replication system to establish
        :py:class:`network.replicable.Replicable` references.

        If the instance_id is registered, take precedence over non-static
        instances.

        :param register_immediately: if registration should occur immediately
        """
        # Try and match an existing instance
        try:
            existing = cls.get_from_graph(instance_id)

        # If we don't find one, make one
        except LookupError:
            existing = None

        else:
            # If we find a locally defined replicable
            # If instance_id was None when created -> not static
            # This may cause issues if IDs are recycled before torn_off / temporary entities are destroyed
            if existing._local_authority:
                # Make the class and overwrite the id
                existing = None

        if existing is None:
            existing = cls(instance_id=instance_id, register_immediately=register_immediately, static=False)
            # Perform incomplete role switch when spawning (later set by server, to include autonomous->simulated conversion)
            roles = existing.roles
            roles.local, roles.remote = roles.remote, roles.local

        return existing

    @classmethod
    def get_id_iterable(cls):
        """Create iterator up to maximum replicable count

        :returns: range up to maximum ID
        :rtype: iterable
        """
        return range(cls._MAXIMUM_REPLICABLES)

    def register(self, instance_id=None, immediately=False):
        """Handles registered of instances.

        Modifies behaviour to allow network priority over local instances.

        Handles edge cases such as static replicables.

        :param instance_id: instance id to register with
        :param register: if registered should be immediate
        """
        # This is not static or replicated then it's local
        if instance_id is None:
            self._local_authority = True
            self._static = False

        # Therefore we will have authority to change things
        if self.__class__.graph_has_instance(instance_id):
            instance = self.__class__.get_from_graph(instance_id)
            # If the instance is not local, then we have a conflict
            error_message = "Authority over instance id {}\
                             cannot be resolved".format(instance_id)
            assert instance._local_authority, error_message

            # Forces reassignment of instance id
            instance.register(None, immediately)

        # Possess the instance id
        super().register(instance_id, immediately)

    def possessed_by(self, other):
        """Called on possession by other replicable

        :param other: other replicable (owner)
        """
        self.owner = other

    def unpossessed(self):
        """Called on unpossession by replicable.

        May be due to death of replicable
        """
        self.owner = None

    def on_registered(self):
        """Called on registered of replicable.

        Registers instance to type list
        """
        super().on_registered()

        self.__class__._by_types[type(self)].append(self)
        ReplicableRegisteredSignal.invoke(target=self)

    def on_unregistered(self):
        """Called on unregistered of replicable.

        Removes instance from type list
        """
        super().on_unregistered()

        self.unpossessed()

        self.__class__._by_types[type(self)].remove(self)
        ReplicableUnregisteredSignal.invoke(target=self)

    def on_notify(self, name):
        """Called on notifier attribute change

        :param name: name of attribute that has changed
        """
        if 0:
            print("{} attribute of {} was changed by the network".format(name,
                                                 self.__class__.__name__))

    def conditions(self, is_owner, is_complaint, is_initial):
        """Condition generator that determines replicated attributes.

        Attributes yielded are still subject to conditions before sending

        :param is_owner: if the current :py:class:`network.channel.Channel`\
        is the owner
        :param is_complaint: if any complaining variables have been changed
        :param is_initial: if this is the first replication for this target
        """
        if is_complaint or is_initial:
            yield "roles"
            yield "owner"
            yield "torn_off"

    def __description__(self):
        """Returns a hash-like description for this replicable.

        Used by replication system to determine if reference has changed
        :rtype: int"""
        return hash(self.instance_id)

    def __repr__(self):
        class_name = self.__class__.__name__

        if not self.registered:
            return "(Replicable {})".format(class_name)

        return "(Replicable {0}: id={1.instance_id})".format(class_name, self)


# Circular Reference on attribute
Replicable.owner.data_type = Replicable
