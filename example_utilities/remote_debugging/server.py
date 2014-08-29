from network.enums import Netmodes
from network.simple_network import respect_interval, SimpleNetwork
from network.world_info import WorldInfo

from .replicables import RemoteTerminal


class Rules:

    def __init__(self, reference):
        self.reference = reference

    def pre_initialise(self, addr, netmode):
        pass

    def post_initialise(self, connection):
        terminal = RemoteTerminal(register=True)
        terminal.data['reference'] = self.reference
        return terminal

    def is_relevant(self, conn, replicable):
        return True


def setup(reference):
    WorldInfo.netmode = Netmodes.server
    WorldInfo.rules = Rules(reference)
    network = SimpleNetwork("", 1200)

    return network


def application():
    """Example application with network debugging"""

    # Some object to pass to the remote terminal
    reference_data = {"name": "John Smith"}

    # Network data
    network = setup(reference_data)
    update_network = respect_interval(1 / 60, network.step)

    while True:
        name = reference_data['name']
        print("Running app as {}".format(name))
        update_network()


if __name__ == "__main__":
    application()