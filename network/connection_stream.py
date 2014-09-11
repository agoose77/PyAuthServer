from .decorators import with_tag
from .enums import Netmodes
from .tagged_delegate import DelegateByNetmode
from .world_info import WorldInfo


class ConnectionStream(DelegateByNetmode):
    pass


# TODO
# rename connection_interfaces to remove the ultimate s
# restore connection code to stream
# add stream delegation methods

@with_tag(Netmodes.server)
class ServerStream(ConnectionStream):

    def __init__(self):
        self.replicable = WorldInfo.rules.post_initialise(self)
        # Replicable is boolean false until registered
        # User can force register though!