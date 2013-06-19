from .bases import Enum
from contextlib import contextmanager

class Netmodes(metaclass=Enum):
    values ="server", "client", "listen", "single"

class Roles(metaclass=Enum):
    values = "none", "simulated_proxy", "autonomous_proxy", "authority"
    
    __slots__ = "local", "remote", "context"
    
    def __init__(self, local, remote):
        self.local = local
        self.remote = remote
        self.context = None
    
    def __description__(self):
        return hash((self.context, self.local, self.remote))
    
    def __repr__(self):
        return "Roles: Local: {}, Remote: {}".format(self.__class__[self.local], self.__class__[self.remote])
    
    @contextmanager
    def switched(self):
        self.remote, self.local = self.local, self.remote
        if self.local == Roles.autonomous_proxy and not self.context:
            self.local = self.simulated_proxy
            fix_autonomous = True
        else:
            fix_autonomous = False
        yield
        if fix_autonomous:
            self.local = Roles.autonomous_proxy
        self.remote, self.local = self.local, self.remote
        

class Protocols(metaclass=Enum):
    values = "auth_failure", "auth_success", "request_auth", "replication_init", "replication_del", "replication_update", "method_invoke"
    
class ConnectionStatus(metaclass=Enum):
    values = "deleted", "timeout", "disconnected", "handshake", "connected"