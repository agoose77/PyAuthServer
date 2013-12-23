from .type_register import TypeRegister


class NetworkError(Exception, metaclass=TypeRegister):
    pass


class ConnectionTimeoutError(NetworkError):
    pass


class ReplicableAccessError(NetworkError):
    pass
