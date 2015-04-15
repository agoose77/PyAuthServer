from panda_game_system.game_loop import Client, Server

from .actors import *

classes = dict(server=Server, client=Client)

from network.world_info import WorldInfo
from network.rules import ReplicationRulesBase
from network.enums import Netmodes

from game_system.controllers import PawnController, PlayerPawnController
from game_system.entities import Actor
from game_system.replication_info import ReplicationInfo


class Rules(ReplicationRulesBase):

    def pre_initialise(self, addr, netmode):
        return

    def post_disconnect(self, conn, replicable):
        replicable.deregister()

    def post_initialise(self, replication_stream):
        print("CON")
        cont = PlayerPawnController(register_immediately=True)
        cont.possess(TestActor())
        return cont

    def is_relevant(self, connection, replicable):
        if isinstance(replicable, PawnController):
            return False

        elif isinstance(replicable, Actor):
            return True

        elif isinstance(replicable, ReplicationInfo):
            return True

        elif replicable.always_relevant:
            return True


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
    TestActor()
    game_loop.delegate()
    del game_loop