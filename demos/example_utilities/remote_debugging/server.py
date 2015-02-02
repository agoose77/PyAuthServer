##NETWORK STUFF
from network.enums import Netmodes
from network.simple_network import respect_interval, SimpleNetwork
from network.world_info import WorldInfo

from .replicables import RemoteTerminal


class Rules:

    def pre_initialise(self, addr, netmode):
        pass

    def post_initialise(self, connection):
        terminal = RemoteTerminal(register_immediately=True)
        return terminal

    def post_disconnect(self, connection, replicable):
        print("disconnected")

    def is_relevant(self, conn, replicable):
        return True


def application():
	WorldInfo.netmode = Netmodes.server
	WorldInfo.rules = Rules()

	network = SimpleNetwork("", 1200)
	update_network = respect_interval(1 / 60, network.step)
	
	RemoteTerminal.counter = 0
	
	while True:
		update_network()