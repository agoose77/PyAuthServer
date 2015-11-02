from network.enums import Netmodes
from network.network import NetworkManager, DefaultTransport, UnreliableSocketWrapper

from demos.v2.entities import SomeEntity

from game_system.fixed_timestep import FixedTimeStepManager
from panda_game_system.world import World

from direct.showbase.ShowBase import ShowBase

game_loop = FixedTimeStepManager()
base = ShowBase()


def server():
    world = World(Netmodes.server, 60, "D:/PyCharmProjects/PyAuthServer/demos/v2/")

    class Rules:

        def pre_initialise(self, connection_info):
            pass

        def post_initialise(self, replication_manager):
            world = replication_manager.world
            scene = world.scenes["Scene"]

            replicable = scene.add_replicable(SomeEntity)
            replication_manager.set_root_for_scene(scene, replicable)
            print("SPAWN")

        def is_relevant(self, replicable):
            return True

    world.rules = Rules()

    scene = world.add_scene("Scene")

    box = scene.add_replicable(SomeEntity)
    box.transform.world_position = (0, 10, -5)
    box.physics.mass = 0

    network = NetworkManager(world, "localhost", 1200)

    # network._transport = UnreliableSocketWrapper(network._transport)
    # world.messenger.add_subscriber("tick", network._transport.update)

    base.cam.set_pos(0, -35, 0)

    return network, world


def client():
    world = World(Netmodes.client, 60, "D:/PyCharmProjects/PyAuthServer/demos/v2/")
    network = NetworkManager(world, "localhost", 0)

    # network._transport = UnreliableSocketWrapper(network._transport)
    # world.messenger.add_subscriber("tick", network._transport.update)

    base.cam.set_pos(0, -35, 0)
    network.connect_to("localhost", 1200)

    return network, world


def main():
    i = 0

    cnet, cworld = client()
    snet, sworld = server()

    while True:
        cnet.receive()
        snet.receive()
        base.taskMgr.step()

        cworld.tick()
        sworld.tick()

        is_net_tick = not i % 3
        snet.send(is_net_tick)
        cnet.send(is_net_tick)
        i += 1
        dt = yield

loop = main()
next(loop)

# from panda3d.bullet import BulletRigidBodyNode, BulletBoxShape
# n = BulletRigidBodyNode()
# n.addShape(BulletBoxShape((2, 2, 2)))
# from panda3d.core import NodePath
# n = NodePath(n)
# n.writeBamFile("Cube.bam")

game_loop.on_step = loop.send
game_loop.run()
