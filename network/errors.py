from .type_register import TypeRegister  # @UnusedImport

__all__ = ['NetworkError', 'ConnectionTimeoutError', 'ReplicableAccessError']


class NetworkError(Exception, metaclass=TypeRegister):
    subclasses = {}


class ConnectionTimeoutError(NetworkError):
    pass


class ReplicableAccessError(NetworkError):
    pass
