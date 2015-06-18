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
from game_system.ai.sensors import SightSensor
from game_system.ai.working_memory import WMFact
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

        closest_pickup = min(Replicable.subclass_of_type(AmmoPickup), key=distance_key)
        working_memory = self.sensor.controller.working_memory

        try:
            fact = working_memory.find_single_fact('nearest_ammo')

        except KeyError:
            fact = WMFact('nearest_ammo')
            working_memory.add_fact(fact)

        fact.data = closest_pickup
        fact._uncertainty_accumulator = 0.0


class GOTOState(State):

    def __init__(self, controller):
        super().__init__("GOTO")

        self.controller = controller
        self.request = None

        self.waypoint_margin = 0.5
        self.target_margin = 2

    def find_path_to(self, source, target):
        navmesh = next(iter(Replicable.subclass_of_type(Navmesh)))
        return navmesh.navmesh.find_path(source, target)

    def draw_path(self, path):
        from panda3d.core import LineSegs, Vec4, Vec3
        path = [Vec3(*v) for v in path]
        segs = LineSegs( )
        segs.setThickness( 2.0 )
        segs.setColor( Vec4(1,1,0,1) )
        segs.moveTo( path[0] )
        for p in path[1:]:
            segs.drawTo(p)
        node = segs.create( )
        render.attachNewNode(node)

    def update(self):
        request = self.request

        if request is None:
            return

        if request.status != EvaluationState.running:
            return

        # We need a pawn to perform GOTO action
        pawn = self.controller.pawn
        if pawn is None:
            return

        pawn_position = pawn.transform.world_position
        target_position = request.target.transform.world_position

        try:
            path = request._path

        except AttributeError:
            request._path = path = self.find_path_to(pawn_position, target_position)
            self.draw_path(path)

        target_distance = (target_position - pawn_position).length

        while path:
            waypoint_position = path[0]
            to_waypoint = waypoint_position - pawn_position

            # Update request
            distance = to_waypoint.xy.length
            request.distance_to_target = distance

            if distance < self.waypoint_margin:
                path[:] = path[1:]

            else:
                pawn.physics.world_velocity = to_waypoint.normalized() * 5

                if target_distance > self.target_margin:
                    return
                break

        request.status = EvaluationState.success
        pawn.physics.world_velocity = to_waypoint * 0


class ZombCont(AIPawnController):
    actions = [GetNearestAmmoPickup()]
    goals = [FindAmmoGoal()]

    def on_initialised(self):
        super().on_initialised()

        self.fsm = FiniteStateMachine()
        self.fsm.add_state(GOTOState(self))

        self.blackboard['has_ammo'] = False
        self.blackboard['ammo'] = 0

        view_sensor = SightSensor()
        self.sensor_manager.add_sensor(view_sensor)

        interpreter = PickupInterpreter()
        view_sensor.add_interpreter(interpreter)


def setup_map():
    floor = Map()
    floor.transform._nodepath.set_color(0.3, 0.3, 0.0)
    #floor.transform._nodepath.set_scale(10)
    floor.physics.mass = 0.0
    floor.mass = 0.0

    navmesh = TestNavmesh()

    pickup = AmmoPickup()
    pickup.transform.world_position = [0, 20, 1]
    pickup.physics.mass = 0.0
    floor.transform._nodepath.set_color(1, 0.0, 0.0)
    #
    cont = ZombCont()
    # base.toggleWireframe()
    # from game_system.timer import Timer
    #
    # timer = Timer(0.1)
    # view = next(s for s in cont.sensor_manager._sensors if isinstance(s, SightSensor))
    # timer.on_target = lambda: cont.sensor_manager.remove_sensor(view)

    pawn = TestAI()
    pawn.transform.world_position = [0, -10, 1]
    cont.possess(pawn)

    from panda3d.bullet import BulletDebugNode
    debugNode = BulletDebugNode('Debug')
    debugNode.showWireframe(True)
    debugNode.showConstraints(True)
    debugNode.showBoundingBoxes(False)
    debugNode.showNormals(False)
    debugNP = render.attachNewNode(debugNode)
    debugNP.show()

    base.physics_system.world.set_debug_node(debugNP.node())

    from panda3d.core import DirectionalLight, Vec4
    # Directional light 01
    directionalLight = DirectionalLight('directionalLight')
    directionalLight.setColor(Vec4(0.8, 0.2, 0.2, 1))
    directionalLightNP = render.attachNewNode(directionalLight)
    # This light is facing backwards, towards the camera.
    directionalLightNP.setHpr(180, -20, 0)
    render.setLight(directionalLightNP)


def init_game():
    if WorldInfo.netmode == Netmodes.server:
        base.cam.set_pos((0, -45, 10))
        base.cam.set_hpr(0, -10, 0)
        setup_map()

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