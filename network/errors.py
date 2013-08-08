from .registers import TypeRegister

class NetworkError(Exception, metaclass=TypeRegister):
    pass

class LatencyInducedError(NetworkError):
    pass
    
