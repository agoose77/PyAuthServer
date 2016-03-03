from .factory import NamedSubclassTracker

__all__ = ['NetworkError', 'ConnectionTimeoutError', 'ReplicableAccessError']


class NetworkError(Exception, metaclass=NamedSubclassTracker):
    pass


class ConnectionTimeoutError(NetworkError):
    pass


class ReplicableAccessError(NetworkError):
    pass


class ExplicitReplicableIdCollisionError(Exception):
    pass
