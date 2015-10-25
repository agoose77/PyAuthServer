from network.enums import Netmodes
from network.network import NetworkManager

from demos.v2.entities import SomeEntity

from game_system.fixed_timestep import FixedTimeStepManager
from panda_game_system.world import World

from direct.showbase.ShowBase import ShowBase


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

game_loop = FixedTimeStepManager()
base = ShowBase()

server_world = World(Netmodes.server, 60, "D:/pycharmprojects/pyauthserver/demos/v2/")
server_world.rules = Rules()
server_network = NetworkManager(server_world, "localhost", 1200)

server_scene = server_world.add_scene("Scene")
server_replicable = server_scene.add_replicable(SomeEntity)
server_replicable.score = 100


def main():
    i = 0
    while True:
        server_network.receive()
        base.taskMgr.step()
        server_world.tick()
        server_network.send(not i % 3)
        i += 1
        dt = yield

loop = main()
next(loop)

game_loop.on_step = loop.send
game_loop.run()
