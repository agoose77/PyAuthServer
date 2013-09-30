from .type_register import TypeRegister


class NetworkError(Exception, metaclass=TypeRegister):
    pass


class TimeoutError(NetworkError):
    pass


class ReplicableAccessError(NetworkError):
    pass
