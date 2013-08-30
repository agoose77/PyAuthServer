from .network import WorldInfo
from .actors import Replicable, Controller
from .descriptors import StaticValue, Attribute
from .enums import Roles, Netmodes
    
class BaseGameInfo(Replicable):
    roles = Attribute(
                      Roles(Roles.authority, Roles.none)
                      )
    
    def broadcast(self, sender, message):
        if not self.allows_broadcast(sender, message):
            return
        
        for replicable in WorldInfo.subclass_of(Controller):
            
            replicable.receive_broadcast(sender, message)
    
    def allows_broadcast(self, sender, message):
        return len(message) <= 255
    
    def pre_initialise(self, addr, netmode):
        return NotImplemented
        
    def post_initialise(self, connection):
        return NotImplemented
    
    def on_disconnect(self, replicable):
        return NotImplemented
    
    def is_relevant(self, conn, replicable):        
        return NotImplemented