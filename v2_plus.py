from network_2.world import World
from network_2.replicable import Replicable
from network_2.enums import Netmodes, Roles
from network_2.replication import Serialisable
from network_2.network import NetworkManager


class Replicable1(Replicable):

    def do_work(self, x: int, y: (str, dict(max_length=255))) -> Netmodes.server:
        print("PARENT WORK")


class Replicable2(Replicable1):
    score = Serialisable(data_type=int, flag_on_assignment=True)
    roles = Serialisable(Roles(Roles.authority, Roles.simulated_proxy))

    def can_replicate(self, is_owner, is_initial):
        yield "score"
        yield "roles"

    def do_work(self, x: int, y: (str, dict(max_length=255))) -> Netmodes.server:
        super().do_work(x, y)


class Rules:
    def pre_initialise(self, connection_info):
        pass

    def post_initialise(self, replication_manager):
        pass

    def is_relevant(self, replicable):
        return True


world2 = World(Netmodes.server)
world2.rules = Rules()
scene2 = world2.add_scene("Scene")
replicable2 = scene2.add_replicable("Replicable2")
net2 = NetworkManager(world2, "localhost", 1200)

world = World(Netmodes.client)
scene = world.add_scene("Scene")
net = NetworkManager(world, "localhost", 0)
net.connect_to("localhost", 1200)

scene.messenger.add_subscriber("replicable_added", lambda p: print("Replicable created", p))

replicable2.score = 15

import time
net.send(True)
net2.receive()
net2.send(True)
net.receive()

print(scene.replicables[0].score)

