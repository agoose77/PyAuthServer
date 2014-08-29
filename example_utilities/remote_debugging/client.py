from network.enums import Netmodes
from network.simple_network import SimpleNetwork
from network.world_info import WorldInfo

from .replicables import RemoteTerminal
from .tools import input_multiple


def run_interface():
    terminals = WorldInfo.subclass_of(RemoteTerminal)
    if not terminals:
        return

    terminal = terminals[0]
    command = input_multiple(">>> ")
    terminal.execute(command)


def application(peer_data=("localhost", 1200)):
    WorldInfo.netmode = Netmodes.client
    network = SimpleNetwork("", 0)

    network.on_initialised = lambda: network.connect_to(peer_data)
    network.on_update = run_interface

    network.start()

if __name__ == "__main__":
    application()