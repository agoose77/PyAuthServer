from .factory import SubclassRegistryMeta

__all__ = ['NetworkError', 'ConnectionTimeoutError', 'ReplicableAccessError']


class NetworkError(Exception, metaclass=SubclassRegistryMeta):
    pass


class ConnectionTimeoutError(NetworkError):
    pass


class ReplicableAccessError(NetworkError):
    pass


class ExplicitReplicableIdCollisionError(Exception):
    pass
