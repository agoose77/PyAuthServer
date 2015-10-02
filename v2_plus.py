from network_2.world import World
from network_2.replicable import Replicable
from network_2.enums import Netmodes, Roles
from network_2.replication import Serialisable


class Replicable1(Replicable):

    def do_work(self, x: int, y: (str, dict(max_length=255))) -> Netmodes.server:
        print("PARENT WORK")


class Replicable2(Replicable1):
    score = Serialisable(data_type=int, flag_on_assignment=True)

    def do_work(self, x: int, y: (str, dict(max_length=255))) -> Netmodes.server:
        super().do_work(x, y)


world = World(Netmodes.client)
scene = world.add_scene("Scene")
replicable = scene.add_replicable("Replicable2")
replicable.roles.local = Roles.simulated_proxy
replicable.do_work(1, "hi")

replicable.score = 12