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


def init_game():
    if WorldInfo.netmode == Netmodes.server:
        floor = TestActor(register_immediately=True)
        floor.transform.world_position = [0, 30, -1]

        floor.physics.mass = 0.0
        floor.mass = 0.0

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
    game_loop.delegate()
    del game_loop