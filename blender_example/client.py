from bge_network import Network, BaseRules, Pawn, WorldInfo, Netmodes

WorldInfo.netmode = Netmodes.client

network = Network("localhost", 0)

network.connect_to(("localhost", 1200))

def main():
    network.receive()
    Pawn.update_graph()
    network.send()