from network.enums import Netmodes
from network.simple_network import SimpleNetwork
from network.world_info import WorldInfo

from functools import partial

from .replicables import RemoteTerminal
from .tools import multiline_input


def run_interface(namespace):
    terminals = WorldInfo.subclass_of(RemoteTerminal)
    if not terminals:
        return

    # Blocking inputs
    if namespace.get("waiting"):
        return

    terminal = terminals[0]
    command = multiline_input()

    namespace['waiting'] = True

    mark_received = lambda: namespace.__setitem__('waiting', False)

    if command:
        terminal.execute(command, mark_received)


def application(peer_data=("localhost", 1200)):
    WorldInfo.netmode = Netmodes.client
    network = SimpleNetwork("", 0)

    namespace = {}

    network.on_initialised = lambda: print("CONN") or network.connect_to(peer_data)
    network.on_update = partial(run_interface, namespace)

    network.start()

if __name__ == "__main__":
    application()