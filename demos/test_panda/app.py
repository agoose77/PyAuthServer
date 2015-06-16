try:
    import bge

except ImportError:
    from panda_game_system.game_loop import Client, Server
    from .ui import UI; UI()

else:
    from bge_game_system.game_loop import Client, Server

from network.connection import Connection
from network.world_info import WorldInfo
from network.rules import ReplicationRulesBase
from network.enums import Netmodes

from game_system.controllers import PawnController, AIPawnController
from game_system.clock import Clock
from game_system.entities import Actor
from game_system.ai.sensors import SightSensor, WMFact
from game_system.replication_info import ReplicationInfo

from .actors import *
from .controllers import TestPandaPlayerController


classes = dict(server=Server, client=Client)


class Rules(ReplicationRulesBase):

    def pre_initialise(self, addr, netmode):
        return

    def post_disconnect(self, conn, replicable):
        replicable.deregister()

    def post_initialise(self, replication_stream):
        cont = TestPandaPlayerController()
        cont.possess(TestActor())
        return cont

    def is_relevant(self, connection, replicable):
        if isinstance(replicable, PawnController):
            return False

        elif isinstance(replicable, (Actor, ReplicationInfo, Clock)):
            return True

        elif replicable.always_relevant:
            return True


from .planner import *
from game_system.ai.sensors import SightInterpreter


class PickupInterpreter(SightInterpreter):

    def __init__(self):
        self.sensor = None

    def handle_visible_actors(self, actors):
        if not actors:
            return

        pawn = self.sensor.controller.pawn
        if pawn is None:
            return

        pawn_position = pawn.transform.world_position
        distance_key = lambda a: (a.transform.world_position - pawn_position).length_squared

        closest_pickup = min(actors, key=distance_key)
        working_memory = self.sensor.controller.working_memory

        try:
            fact = working_memory.find_single_fact('nearest_ammo')

        except KeyError:
            fact = WMFact('nearest_ammo')
            working_memory.add_fact(fact)

        fact.data = closest_pickup
        fact._uncertainty_accumulator = 0.0

        print(fact)


class ZombCont(AIPawnController):
    actions = [GetNearestAmmoPickup()]
    goals = [FindAmmoGoal()]

    def on_initialised(self):
        super().on_initialised()

        self.blackboard['has_ammo'] = False
        self.blackboard['ammo'] = 0

        view_sensor = SightSensor()
        self.sensor_manager.add_sensor(view_sensor)

        interpreter = PickupInterpreter()
        view_sensor.add_interpreter(interpreter)


def init_game():
    if WorldInfo.netmode == Netmodes.server:
        base.cam.set_pos((0, -60, 0))

        floor = TestActor()
        floor.transform.world_position = [0, 0, -11]
        floor.transform._nodepath.set_color(0.3, 0.3, 0.0)
        floor.transform._nodepath.set_scale(10)
        floor.physics.mass = 0.0
        floor.mass = 0.0

        pickup = AmmoPickup()
        pickup.transform.world_position = [0, 12, 1]
        pickup.physics.mass = 0.0
        floor.transform._nodepath.set_color(1, 0.0, 0.0)
        #
        cont = ZombCont()

        from game_system.timer import Timer

        timer = Timer(0.1)
        view = next(s for s in cont.sensor_manager._sensors if isinstance(s, SightSensor))
        timer.on_target = lambda: cont.sensor_manager.remove_sensor(view)

        omb = TestActor()
        omb.transform.world_position = [0, 0, 1]
        cont.possess(omb)

        pass

    else:
        Connection.create_connection("localhost", 1200)


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

    # model = loader.loadModel(f)
    # model.reparentTo(base.render)
    #
    # from panda3d.core import PointLight
    # plight = PointLight('plight')
    # plight.setColor((1, 1, 1, 1))
    # plnp = render.attachNewNode(plight)
    # plnp.setPos(10, 20, 0)
    # render.setLight(plnp)

    game_loop.delegate()
    del game_loop