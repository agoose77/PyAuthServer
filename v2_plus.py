from network_2.world import World
from network_2.handlers import TypeFlag
from network_2.replicable import Replicable
from network_2.enums import Netmodes


class Replicable1(Replicable):

    def do_work(self, x: int, y: (str, dict(max_length=255))) -> Netmodes.server:
        print("PARENT WORK")


class Replicable2(Replicable1):

    def do_work(self, x: int, y: (str, dict(max_length=255))) -> Netmodes.server:
        print("WORK", x, y)
        super().do_work(x, y)


world = World(Netmodes.client)
scene = world.add_scene("Scene")
replicable = scene.add_replicable("Replicable2")
replicable.do_work(1, "hi")


print(replicable.replicated_function_queue)

