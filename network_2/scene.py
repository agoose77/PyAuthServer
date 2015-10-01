from collections import OrderedDict

from .factory import ProtectedInstance, UniqueIDPool
from .messages import MessagePasser
from .replicable import Replicable


class Scene(ProtectedInstance):

    def __init__(self, world, name):
        self.world = world
        self.name = name

        self.messenger = MessagePasser()
        self.replicables = OrderedDict()

        self._unique_ids = UniqueIDPool(255)

    def _contest_id(self, unique_id, contestant, existing):
        self.replicables[unique_id] = contestant

        # Re-associate existing
        unique_id = self._unique_ids.take()
        with Replicable._grant_authority():
            existing.change_unique_id(unique_id)

        self.replicables[unique_id] = existing

    def add_replicable(self, cls_name, unique_id=None):
        replicable_cls = Replicable.subclasses[cls_name]

        if unique_id is None:
            unique_id = self._unique_ids.take()
            is_static = False
        
        else:
            is_static = True

        with Replicable._grant_authority():
            replicable = replicable_cls(self, unique_id, is_static)

        self.replicables[unique_id] = replicable
        self.messenger.send("replicable_added", replicable)

        return replicable

    def remove_replicable(self, replicable):
        self.messenger.send("replicable_removed", replicable)

        unique_id = replicable.unique_id
        self.replicables.pop(unique_id)
        self._unique_ids.retire(unique_id)

        replicable.on_destroyed()

    def __repr__(self):
        return "<'{}' scene>".format(self.name)


