from network.enums import Netmodes
from network.network import NetworkManager

from demos.v2.entities import SomeEntity

from game_system.fixed_timestep import FixedTimeStepManager
from panda_game_system.world import World

from direct.showbase.ShowBase import ShowBase

game_loop = FixedTimeStepManager()
base = ShowBase()


netmode = Netmodes.client
world = World(netmode, 60, "D:/Users/Angus/Documents/PyCharmProjects/PyAuthServer/demos/v2/")

if netmode == Netmodes.server:

    class Rules:

        def pre_initialise(self, connection_info):
            pass

        def post_initialise(self, replication_manager, root_replicables):
            world = replication_manager.world
            scene = world.scenes["Scene"]

            replicable = scene.add_replicable(SomeEntity)
            root_replicables.add(replicable)
            print("SPAWN")

        def is_relevant(self, replicable):
            return True

    world.rules = Rules()

    scene = world.add_scene("Scene")
    replicable = scene.add_replicable(SomeEntity)

    box = scene.add_replicable(SomeEntity)
    box.transform.world_position = (0, 10, -5)
    box.physics.mass = 0

    # Timer
    timer = scene.add_timer(3)
    #timer.on_elapsed = lambda: server_scene.remove_replicable(box)

    timer = scene.add_timer(1)
    #timer.on_elapsed = lambda: replicable.mesh.change_mesh("Sphere")

network = NetworkManager(world, "localhost", 1200 if netmode==Netmodes.server else 0)
base.cam.set_pos(0, -35, 0)

if netmode == Netmodes.client:
    network.connect_to("localhost", 1200)

def main():
    i = 0
    while True:
        network.receive()
        base.taskMgr.step()
        world.tick()
        network.send(not i % 3)
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
