__all__ = ['ReplicationRulesBase']


class ReplicationRulesBase:
    """Base class for replication rules"""

    def pre_initialise(self, address):
        raise NotImplementedError

    def post_initialise(self, replication_manager):
        raise NotImplementedError

    def post_disconnected(self, replication_manager, root_replicable):
        raise NotImplementedError

    def is_relevant(self, root_replicable, replicable):
        raise NotImplementedError
