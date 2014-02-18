from .containers import AttributeStorageContainer, RPCStorageContainer
from .descriptors import Attribute
from .enums import Roles, Netmodes
from .decorators import simulated
from .replicable_register import ReplicableRegister
from .signals import (ReplicableRegisteredSignal, ReplicableUnregisteredSignal,
                     UpdateSignal)

from collections import defaultdict

__all__ = ['Replicable', '_WorldInfo', 'WorldInfo']


class Replicable(metaclass=ReplicableRegister):
    '''Replicable base class
    Holds record of instantiated replicables and replicable types
    Default method for notification and generator for conditions.
    Additional attributes for attribute values (from descriptors)
    And complaining attributes'''

    _MAXIMUM_REPLICABLES = 255

    subclasses = {}
    roles = Attribute(
                      Roles(
                            Roles.authority,  # @UndefinedVariable
                            Roles.none  # @UndefinedVariable
                            ),
                      notify=True,
                      )
    owner = Attribute(type_of=None, complain=True, notify=True)

    # Dictionary of class-owned instances
    _by_types = defaultdict(list)

    def __init__(self, instance_id=None, register=False,
                 static=True, **kwargs):
        # If this is a locally authoritative
        self._local_authority = False

        # If this is a static mapping (requires static flag and a matchable ID)
        self._static = static and instance_id is not None

        # Setup the attribute storage
        self.attribute_storage = AttributeStorageContainer(self)
        self.rpc_storage = RPCStorageContainer(self)

        self.attribute_storage.register_storage_interfaces()
        self.rpc_storage.register_storage_interfaces()

        self.owner = None

        self.relevant_to_owner = True
        self.always_relevant = False

        self.replication_priority = 1.0
        self.replication_update_period = 1 / 20

        # Instantiate parent (this is when the creation callback may be called)
        super().__init__(instance_id=instance_id, register=register,
                         allow_random_key=True, **kwargs)

    @property
    def uppermost(self):
        '''Determines if a connection owns this replicable
        Searches for Replicable with same network id as our Controller'''
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
    def create_or_return(cls, base_cls, instance_id, register=True):
        '''Called by the replication system, assumes non static if creating
        Creates a replicable if it is not already instantiated
        @param base_cls: base class of replicable to instantiate
        @param register: if registration should occur immediately'''
        # Try and match an existing instance
        try:
            existing = cls.get_from_graph(instance_id)

        # If we don't find one, make one
        except LookupError:
            return base_cls(instance_id=instance_id,
                            register=register, static=False)

        else:
            # If we find a locally defined replicable
            # If instance_id was None when created -> not static
            if existing._local_authority:
                # Make the class and overwrite the id
                return base_cls(instance_id=instance_id,
                                register=register, static=False)

            return existing

    def validate_id(self, instance_id):
        return instance_id <= self._MAXIMUM_REPLICABLES

    def request_registration(self, instance_id):
        '''Handles registration of instances
        Modifies behaviour to allow network priority over local instances
        Handles edge cases such as static replicables
        @param instance_id: instance id to register with
        @param verbose: if verbose debugging should occur'''
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
            instance.request_registration(None)

        # Possess the instance id
        super().request_registration(instance_id)

    def possessed_by(self, other):
        '''Called on possession by other replicable
        @param other: other replicable (owner)'''
        self.owner = other

    def unpossessed(self):
        '''Called on unpossession by replicable
        May be due to death of replicable'''
        pass

    def on_registered(self):
        '''Called on registration of replicable
        Registers instance to type list'''
        super().on_registered()

        self.__class__._by_types[type(self)].append(self)
        ReplicableRegisteredSignal.invoke(target=self)

    def on_unregistered(self):
        '''Called on unregistration of replicable
        Removes instance from type list'''
        super().on_unregistered()

        self.__class__._by_types[type(self)].remove(self)
        ReplicableUnregisteredSignal.invoke(target=self)

    def on_notify(self, name):
        '''Called on notifier attribute change
        @param name: name of attribute that has changed'''
        if 0:print("{} attribute of {} was changed by the network".format(name,
                                                 self.__class__.__name__))

    def conditions(self, is_owner, is_complaint, is_initial):
        '''Condition generator that determines replicated attributes
        Attributes yielded are still subject to conditions before sending
        @param is_owner: if the current replicator is the owner
        @param is_complaint: if any complaining variables have been changed
        @param is_initial: if this is the first replication for this target '''
        if is_complaint or is_initial:
            yield "roles"
            yield "owner"

    def __description__(self):
        '''Returns a hash-like description for this replicable
        Used to check if the value of a replicated reference has changed'''
        return hash(self.instance_id)

    def __repr__(self):
        if not self.registered:
            return "(Replicable {})".format(
                    self.__class__.__name__)

        return ("(Replicable {0}: id={1.instance_id})"
                .format(self.__class__.__name__, self))


class _WorldInfo(Replicable):
    '''Holds info about game state'''

    _MAXIMUM_TICK = (2 ** 32 - 1)
    _ID = 255

    roles = Attribute(
                      Roles(
                            Roles.authority,  # @UndefinedVariable
                            Roles.simulated_proxy  # @UndefinedVariable
                            )
                      )

    elapsed = Attribute(0.0, complain=False)
    tick_rate = Attribute(1000, complain=True, notify=True)

    def on_initialised(self):
        self._cache = {}

        self.clock_correction = 0.0
        self.rules = None
        self.netmode = Netmodes.server
        self.always_relevant = True

    @ReplicableRegisteredSignal.global_listener
    @simulated
    def cache_replicable(self, target):
        for cls_type, values in self._cache.items():
            if isinstance(target, cls_type):
                values.append(target)

    @ReplicableUnregisteredSignal.global_listener
    @simulated
    def uncache_replicable(self, target):
        for values in self._cache.values():
            if target in values:
                values.remove(target)

    def conditions(self, is_owner, is_complain, is_initial):
        yield from super().conditions(is_owner, is_complain, is_initial)

        if is_initial:
            yield "elapsed"

        if is_complain:
            yield "tick_rate"

    @property
    def tick(self):
        return int((self.elapsed + self.clock_correction) * self.tick_rate)

    @simulated
    def subclass_of(self, actor_type):
        '''Returns registered actors that are subclasses of a given type
        @param actor_type: type to compare against'''
        try:
            return self._cache[actor_type]

        except KeyError:
            values = self._cache[actor_type] = [a for a in Replicable if
                                                isinstance(a, actor_type)]
            return values

    @simulated
    def update_clock(self, delta):
        self.elapsed += delta

    @simulated
    def type_is(self, name):
        return Replicable._by_types.get(name)

    replicables = property(Replicable.get_graph_instances)
    get_replicable = simulated(Replicable.get_from_graph)
    has_replicable = simulated(Replicable.graph_has_instance)


# Circular Reference on attribute
Replicable.owner.type = Replicable

WorldInfo = _WorldInfo(_WorldInfo._ID, register=True)
