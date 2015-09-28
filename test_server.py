from network.simple_network import SimpleNetworkManager
from network.enums import Netmodes, Roles
from network.world import World
from network.descriptors import Attribute
from network.rules import ReplicationRulesBase
from network.replicable import Replicable
from network.type_flag import TypeFlag
from network.scene import NetworkScene


class MyReplicable(Replicable):

    roles = Roles(Roles.authority, Roles.autonomous_proxy)
    name = Attribute("")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        print("INIT")

    def conditions(self, is_owner, is_complaint, is_initial):
        yield "name"

    def say(self, message: TypeFlag(str)) -> Netmodes.client:
        print("YO", message)


class Rules(ReplicationRulesBase):

    def __init__(self):
        self.scene = NetworkScene("BaseScene")

    def pre_initialise(self, address):
        print("Welcoming address", address)

    def post_initialise(self, replication_manager): #, replication_manager.associate_replicables
        with self.scene:
            player = MyReplicable()
            replication_manager.take_ownership(player)

        player.name = "Alex"
        player.say("HIYA BYUBBA")
        return player

    def post_disconnected(self, replication_manager, root_replicable):
        raise NotImplementedError

    def is_relevant(self, root_replicable, replicable):
        return True


from time import clock
started = clock()
i = 0

def on_update(app):
    now = clock()

    if now - started > 20:
        app.stop()
        print("STOP")

    global i
    i += 1
    return not (i % 3)


world = World(Netmodes.server)
with world:
    # Simple network loop
    net_manager = SimpleNetworkManager.from_address_info(port=1200)
    net_manager.rules = Rules()

    net_manager.on_update = lambda: on_update(net_manager)
    net_manager.run(timeout=None, update_rate=1/60)
