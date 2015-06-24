try:
    import bge

except ImportError:
    from panda_game_system.game_loop import Client, Server

else:
    from bge_game_system.game_loop import Client, Server

from network.connection import Connection
from network.world_info import WorldInfo
from network.rules import ReplicationRulesBase
from network.enums import Netmodes

from game_system.controllers import PawnController
from game_system.clock import Clock
from game_system.entities import Actor
from game_system.replication_info import ReplicationInfo

from .actors import *
from .controllers import TestPandaPlayerController, TestAIController

from math import radians
from game_system.coordinates import Euler


classes = dict(server=Server, client=Client)


class Rules(ReplicationRulesBase):

    def pre_initialise(self, addr, netmode):
        return

    def post_disconnect(self, conn, replicable):
        replicable.deregister()

    def post_initialise(self, replication_stream):
        pawn = TestActor()
        pawn.transform.world_position = [-3, -10, 1]

        cont = TestPandaPlayerController()
        cont.possess(pawn)
        return cont

    def is_relevant(self, connection, replicable):
        if isinstance(replicable, PawnController):
            return False

        elif isinstance(replicable, (Actor, ReplicationInfo, Clock)):
            return True

        elif replicable.always_relevant:
            return True


def setup_map():
    floor = Map()
    floor.physics.mass = 0.0
    floor.mass = 0.0

    navmesh = TestNavmesh()
    #
    # pickup = AmmoPickup()
    # pickup.transform.world_position = [4, 5, 1]
    # pickup.physics.mass = 0.0
    #
    # pawn = TestAI()
    # pawn.transform.world_position = [-3, -10, 1]
    # pawn.transform.world_orientation = Euler((0, 0, radians(-50)))
    #
    # cont = TestAIController()
    # cont.possess(pawn)
    #
    # # AI 2
    # pawn = Zombie()
    # pawn.transform.world_position = [3, -11, 1]
    # pawn.transform.world_orientation = Euler((0, 0, radians(-50)))
    #
    # cont = TestAIController()
    # cont.possess(pawn)

    for i in range(500):
        pickup = AmmoPickup()
        pickup.transform._nodepath.set_scale(0.1)
        pickup.transform.world_position = navmesh.navmesh.random_point
        pickup.physics.mass = 0.0


def setup_camera():
    base.cam.set_pos((0, -45, 10))
    base.cam.set_hpr(0, -10, 0)


def setup_lighting():
    from panda3d.core import DirectionalLight, Vec4
    # Directional light 01
    directionalLight = DirectionalLight('directionalLight')
    directionalLight.setColor(Vec4(0.2, 0.2, 0.5, 1))
    directionalLightNP = render.attachNewNode(directionalLight)
    # This light is facing backwards, towards the camera.
    directionalLightNP.setHpr(180, -60, 0)
    render.setLight(directionalLightNP)

def init_game():
    if WorldInfo.netmode == Netmodes.server:
        setup_map()

    else:
        Connection.create_connection("localhost", 1200)

    setup_camera()
    setup_lighting()

    from direct.showbase import DirectObject
    class Obj(DirectObject.DirectObject) :

        def __init__(self):
            super().__init__()

            self.accept("mouse1",self.pick)

        def pick(self):
            from network.replicable import Replicable
            from game_system.coordinates import Vector

            try:
                pickup = next(iter(Replicable.subclass_of_type(AmmoPickup)))

            except StopIteration:
                pickup = AmmoPickup()
                pickup.physics.mass = 0

            from panda3d.core import Point3
            pMouse = base.mouseWatcherNode.getMouse()
            pFrom = Point3()
            pTo = Point3()
            base.camLens.extrude(pMouse, pFrom, pTo)

            # Transform to global coordinates
            source = render.getRelativePoint(base.cam, pFrom)
            dest = render.getRelativePoint(base.cam, pTo)

            position = Vector(base.physics_system.world.rayTestClosest(source, dest).get_hit_pos())

            pickup.transform.world_position = position

    Obj()

def run(mode):
    try:
        cls = classes[mode]

    except KeyError:
        print("Unable to start {}".format(mode))
        return

    if mode == "server":
        WorldInfo.rules = Rules()

    else:
        WorldInfo.netmode = Netmodes.client

    game_loop = cls()
    init_game()

    game_loop.delegate()
    del game_loop