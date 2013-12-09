from .containers import AttributeStorageContainer, RPCStorageContainer
from .descriptors import Attribute, StaticValue
from .enums import Roles, Netmodes
from .decorators import simulated
from .replicable_register import ReplicableRegister
from .signals import (ReplicableRegisteredSignal, ReplicableUnregisteredSignal,
                     UpdateSignal)

from collections import defaultdict


class Replicable(metaclass=ReplicableRegister):
    '''Replicable base class
    Holds record of instantiated replicables and replicable types
    Default method for notification and generator for conditions.
    Additional attributes for attribute values (from descriptors)
    And complaining attributes'''
    _by_types = defaultdict(list)

    roles = Attribute(
                      Roles(
                            Roles.authority,
                            Roles.none
                            ),
                      notify=True,
                      )

    always_relevant = False
    irrelevant_to_owner = False

    def __init__(self, instance_id=None,
                 register=False, static=True, **kwargs):
        # If this is a locally authoritative
        self._local_authority = False

        # If this is a static mapping (requires static flag and a matchable ID)
        self._static = static and instance_id is not None

        # Setup the attribute storage
        self.attribute_storage = AttributeStorageContainer(self)
        self.rpc_storage = RPCStorageContainer(self)

        self.attribute_storage.register_storage_interfaces()
        self.rpc_storage.register_storage_interfaces()

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
        while replicable:
            owner = getattr(replicable, "owner", None)
            last, replicable = replicable, owner

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

    def on_initialised(self):
        self.owner = None
        self.always_relevant = False

    def request_registration(self, instance_id, verbose=False):
        '''Handles registration of instances
        Modifies behaviour to allow network priority over local instances
        Handles edge cases such as static replicables
        @param instance_id: instance id to register with
        @param verbose: if verbose debugging should occur'''
        # This is not static or replicated then it's local
        if instance_id is None:
            self._local_authority = True

        # Therefore we will have authority to change things
        if self.__class__.graph_has_instance(instance_id):
            instance = self.__class__.get_from_graph(instance_id)
            # If the instance is not local, then we have a conflict
            error_message = "Authority over instance id {}\
             is unresolveable".format(instance_id)
            assert instance._local_authority, error_message

            # Possess the instance id
            super().request_registration(instance_id)

            if verbose:
                print("Transferring authority of id {} from {} to {}".format(
                                                 instance_id, instance, self))

            # Forces reassignment of instance id
            instance.request_registration(None)
        if verbose:
            print("Create {} with id {}".format(self.__class__.__name__,
                                                instance_id))

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
        self.__class__._by_types[type(self)].append(self)
        ReplicableRegisteredSignal.invoke(target=self)

    def on_unregistered(self):
        '''Called on unregistration of replicable
        Removes instance from type list'''
        self.__class__._by_types[type(self)].remove(self)
        ReplicableUnregisteredSignal.invoke(target=self)

    def on_notify(self, name):
        '''Called on notifier attribute change
        @param name: name of attribute that has changed'''
        print("{} attribute of {} was changed by the network".format(name,
                                                 self.__class__.__name__))

    def conditions(self, is_owner, is_complaint, is_initial):
        '''Condition generator that determines replicated attributes
        Attributes yielded are still subject to conditions before sending
        @param is_owner: if the current replicator is the owner
        @param is_complaint: if any complaining variables have been changed
        @param is_initial: if this is the first replication for this target '''
        if is_complaint or is_initial:
            yield "roles"

    def __description__(self):
        '''Returns a hash-like description for this replicable
        Used to check if the value of a replicated reference has changed'''
        return hash(self.instance_id)


class BaseWorldInfo(Replicable):
    '''Holds info about game state'''
    netmode = Netmodes.server
    rules = None

    roles = Attribute(
                      Roles(
                            Roles.authority,
                            Roles.simulated_proxy
                            )
                      )
    elapsed = Attribute(0.0, complain=False)

    def conditions(self, is_owner, is_complain, is_initial):
        yield from super().conditions(is_owner, is_complain, is_initial)

        if is_initial:
            yield "elapsed"

    @property
    def replicables(self):
        return Replicable.get_graph_instances()

    @simulated
    def subclass_of(self, actor_type):
        '''Returns registered actors that are subclasses of a given type
        @param actor_type: type to compare against'''
        return (a for a in Replicable if isinstance(a, actor_type))

    @simulated
    @UpdateSignal.global_listener
    def update(self, delta):
        self.elapsed += delta

    @simulated
    def type_is(self, name):
        return Replicable._by_types.get(name)

    get_replicable = simulated(Replicable.get_from_graph)
    has_replicable = simulated(Replicable.graph_has_instance)


WorldInfo = BaseWorldInfo(255, register=True)
