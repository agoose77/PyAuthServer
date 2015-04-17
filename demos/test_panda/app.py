from panda_game_system.game_loop import Client, Server

from .actors import *

classes = dict(server=Server, client=Client)

from network.world_info import WorldInfo
from network.rules import ReplicationRulesBase
from network.enums import Netmodes

from game_system.controllers import PawnController, PlayerPawnController
from game_system.entities import Actor
from game_system.replication_info import ReplicationInfo


from panda3d.core import loadPrcFileData

#loadPrcFileData('', 'bullet-filter-algorithm callback')
loadPrcFileData('', 'bullet-enable-contact-events true')


class Rules(ReplicationRulesBase):

    def pre_initialise(self, addr, netmode):
        return

    def post_disconnect(self, conn, replicable):
        replicable.deregister()

    def post_initialise(self, replication_stream):
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

    # Create cube
    cube = TestActor()

    # Create floor
    floor = TestActor(register_immediately=True)
    floor.transform.world_position = [0, 30, -1]
    floor.physics._node.set_mass(0.0)

    game_loop.delegate()
    del game_loop