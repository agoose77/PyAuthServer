from collections import OrderedDict

from .annotations import protected
from .enums import Netmodes
from .errors import ExplicitReplicableIdCollisionError
from .factory import ProtectedInstanceMeta, UniqueIDPool
from .messages import MessagePasser
from .replicable import Replicable


class Scene(metaclass=ProtectedInstanceMeta):

    def __init__(self, world, name):
        self.world = world
        self.name = name

        self.messenger = MessagePasser()
        self.replicables = OrderedDict()

        self._unique_ids = UniqueIDPool(255)

    @protected
    def release_id(self, contested_id):
        """Contest an existing network ID.

        Given that IDs are taken from a pool, any contest of an ID implies that the contestant explicitly requested
        the ID, which suggests that the contestant is a static replicable
        """
        existing_replicable = self.replicables[contested_id]

        if existing_replicable.id_is_explicit:
            raise ExplicitReplicableIdCollisionError(
                "Cannot contest the unique ID of an explicitly assigned replicable: {}".format(existing_replicable))

        # Re-associate existing
        unique_id = self._unique_ids.take()
        with Replicable._grant_authority():
            existing_replicable.change_unique_id(unique_id)

        self.replicables[unique_id] = existing_replicable

        # Send message
        existing_replicable.messenger.send("unique_id_changed", old_unique_id=contested_id, new_unique_id=unique_id)

    def add_replicable(self, replicable_cls, unique_id=None, from_replication=False):
        """Create a Replicable instance and add it to the replicables dictionary.

        :param replicable_cls: class to instantiate for replicable object
        :param unique_id: unique network ID of replicable
        """
        explicit_id = unique_id is not None

        if not explicit_id:
            unique_id = self._unique_ids.take()

        else:
            # Take unique ID from available set
            try:
                self._unique_ids.take(unique_id)

            # ID is already in use
            except ValueError:
                with Scene._grant_authority():
                    self.release_id(unique_id)

        # Just create replicable
        with Replicable._grant_authority():
            replicable = replicable_cls.__new__(replicable_cls, self, unique_id, explicit_id)

        # On clients, netmodes are reversed
        if self.world.netmode == Netmodes.client and from_replication:
            roles = replicable.roles
            roles.local, roles.remote = roles.remote, roles.local

        # Allow notification of creation before initialisation
        self.messenger.send("replicable_created", replicable)

        # Now initialise replicable
        replicable.__init__(self, unique_id, explicit_id)
        self.replicables[unique_id] = replicable
        self.messenger.send("replicable_added", replicable)

        return replicable

    def remove_replicable(self, replicable):
        """Remove Replicable instance from the replicables dictionary.

        Call replicable.on_destroyed() destructor.

        :param replicable: Replicable instance
        """
        unique_id = replicable.unique_id
        self.replicables.pop(unique_id)
        self._unique_ids.retire(unique_id)

        self.messenger.send("replicable_removed", replicable)

        with Replicable._grant_authority():
            replicable.on_destroyed()

        self.messenger.send("replicable_destroyed", replicable)

    @protected
    def on_destroyed(self):
        """Scene destructor.

        Releases all replicables currently tracked.
        """
        # Release all replicables
        while self.replicables:
            replicable = next(iter(self.replicables.values()))
            self.remove_replicable(replicable)

    def __repr__(self):
        return "<'{}' scene>".format(self.name)


