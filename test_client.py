from network.simple_network import SimpleNetworkManager
from network.enums import Netmodes, Roles
from network.world import World
from network.descriptors import Attribute
from network.replicable import Replicable


class MyReplicable(Replicable):

    roles = Roles(Roles.authority, Roles.autonomous_proxy)
    name = Attribute("", notify=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        print("INIT")

    def conditions(self, is_owner, is_complaint, is_initial):
        yield "name"

    def on_notify(self, name):
        print(self.name)


from time import clock
started = clock()
i = 0

def on_update(app):
    now = clock()
    if now - started > 15:
        app.stop()

    global i
    i += 1
    return not (i % 3)


world = World(Netmodes.client)
with world:
    # Simple network loop
    net_manager = SimpleNetworkManager.from_address_info()

    net_manager.on_update = lambda: on_update(net_manager)
    net_manager.connect_to("localhost", 1200)
    net_manager.run(timeout=None, update_rate=1/60)

