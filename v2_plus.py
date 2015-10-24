from network.world import World
from network.enums import Netmodes
from network.network import NetworkManager

from demos.v2.entities import SomeEntity


class Rules:

    def pre_initialise(self, connection_info):
        pass

    def post_initialise(self, replication_manager, root_replicables):
        world = replication_manager.world
        scene = world.scenes["Scene"]

        # replicable = scene.add_replicable(Replicable2)
        # root_replicables.add(replicable)

    def is_relevant(self, replicable):
        return True


server_world = World(Netmodes.server)
server_world.rules = Rules()
server_network = NetworkManager(server_world, "localhost", 1200)

server_scene = server_world.add_scene("Scene")
server_replicable = server_scene.add_replicable(SomeEntity)
server_replicable.score = 100

from game_system.main_loop import FixedTimeStepManager
game_loop = FixedTimeStepManager()


def main():
    i = 0
    while True:
        server_network.receive()
        server_world.tick()
        server_network.send(not i % 3)
        i += 1
        dt = yield

loop = main()
next(loop)

game_loop.on_step = loop.send
game_loop.run()
