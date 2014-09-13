__all__ = ['ReplicationRulesBase']


class ReplicationRulesBase:

    def pre_initialise(self, addr, netmode):
        raise NotImplementedError

    def post_initialise(self, replication_stream):
        raise NotImplementedError

    def post_disconnected(self, replication_stream, replicable):
        raise NotImplementedError

    def is_relevant(self, conn, replicable):
        raise NotImplementedError
