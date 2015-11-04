from network.enums import Netmodes
from network.network import NetworkManager, DefaultTransport, UnreliableSocketWrapper

from demos.v2.replicables import SomeEntity, MyPC

from game_system.fixed_timestep import FixedTimeStepManager
from game_system.replicables import PawnController, ReplicationInfo, Actor

from panda_game_system.world import World
from direct.showbase.ShowBase import ShowBase
from panda3d.core import PStatClient

base = ShowBase()
PStatClient.connect()


def server():
    world = World(Netmodes.server, 60, "D:/Users/Angus/Documents/PyCharmProjects/PyAuthServer/demos/v2/")

    class Rules:

        def pre_initialise(self, connection_info):
            pass

        def post_initialise(self, replication_manager):
            world = replication_manager.world
            scene = world.scenes["Scene"]

            pc = scene.add_replicable(MyPC)
            replication_manager.set_root_for_scene(scene, pc)

            replicable = scene.add_replicable(SomeEntity)
            pc.take_control(replicable)
            replicable.owner = pc

            def rand():
                import random
                return random.randint(-10, 10)

            for i in range(10):
                def add():
                    replicable = scene.add_replicable(SomeEntity)
                    replicable.transform.world_position = (rand(), rand(), 10.0)

                print(i * 0.5)
                timer = scene.add_timer(i * 0.5)
                timer.on_elapsed = add

            print("SPAWN")

        def is_relevant(self, replicable):
            if isinstance(replicable, PawnController):
                return False

            elif isinstance(replicable, (Actor, ReplicationInfo)):
                return True

            elif replicable.always_relevant:
                return True

    world.rules = Rules()

    scene = world.add_scene("Scene")
    scene._root_nodepath.hide()

    box = scene.add_replicable(SomeEntity)
    box.transform.world_position = (0, 10, -5)
    box.physics.mass = 0

    network = NetworkManager(world, "localhost", 1200)
    base.cam.set_pos(0, -85, 0)

    return network, world


def client():
    world = World(Netmodes.client, 60, "D:/Users/Angus/Documents/PyCharmProjects/PyAuthServer/demos/v2/")
    network = NetworkManager(world, "localhost", 0)

    base.cam.set_pos(0, -35, 0)
    network.connect_to("localhost", 1200)

    return network, world


game_loop = FixedTimeStepManager()


def test_input_exit(input_manager):
    from game_system.enums import InputButtons, ButtonStates

    if input_manager.buttons_state[InputButtons.ESCKEY] == ButtonStates.pressed:
        game_loop.stop()


def main():
    i = 0

    cnet, cworld = client()
    snet, sworld = server()

    cworld.messenger.add_subscriber("input_updated", test_input_exit)
    sworld.messenger.add_subscriber("input_updated", test_input_exit)

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
