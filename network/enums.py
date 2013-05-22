from .bases import Enum
 
class Netmodes(metaclass=Enum):
    values ="server", "client", "listen", "single"

class Roles(metaclass=Enum):
    values = "none", "simulated_proxy", "autonomous_proxy", "authority"

class Protocols(metaclass=Enum):
    values = "auth_failure", "auth_success", "request_auth", "replication_init", "replication_del", "replication_update", "method_invoke"
    
class ConnectionStatus(metaclass=Enum):
    values = "deleted", "timeout", "disconnected", "handshake", "connected"