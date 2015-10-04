from network_2.world import World
from network_2.replicable import Replicable
from network_2.enums import Netmodes, Roles
from network_2.replication import Serialisable
from network_2.network import NetworkManager
from network_2.struct import Struct


class Vector(Struct):

    x = Serialisable(0)
    y = Serialisable(0)
    z = Serialisable(0)


class ManyVectors(Struct):
    a = Serialisable(Vector())
    b = Serialisable(Vector())
    c = Serialisable(Vector())
    d = Serialisable(Vector())


class Replicable1(Replicable):

    def do_work(self, x: int, y: (str, dict(max_length=255))) -> Netmodes.server:
        print("PARENT WORK", x, y)

    def do_work2(self, x: int, y: (str, dict(max_length=255))) -> Netmodes.client:
        super().do_work(x, y)


class Replicable2(Replicable1):
    score = Serialisable(data_type=int, flag_on_assignment=True)
    roles = Serialisable(Roles(Roles.authority, Roles.simulated_proxy))
    struct = Serialisable(data_type=ManyVectors)

    def can_replicate(self, is_owner, is_initial):
        yield "score"
        yield "struct"
        yield "roles"

    def on_replicated(self, name):
        print(name)

    def do_work(self, x: int, y: (str, dict(max_length=255))) -> Netmodes.client:
        super().do_work(x, y)


class Rules:

    def pre_initialise(self, connection_info):
        pass

    def post_initialise(self, replication_manager, root_replicables):
        world = replication_manager.world
        scene = world.scenes["Scene"]

        replicable = scene.add_replicable(Replicable2)
        root_replicables.add(replicable)

    def is_relevant(self, replicable):
        print(replicable, "REL?")
        return True


# TODO: enable actor-like replicables cross-platform
# How do resources fit into world-paradigm? (Environment?)
#

server_world = World(Netmodes.server)
server_world.rules = Rules()
server_scene = server_world.add_scene("Scene")
server_replicable = server_scene.add_replicable(Replicable2)
server_network = NetworkManager(server_world, "localhost", 1200)

client_world = World(Netmodes.client)
client_scene = client_world.add_scene("Scene")
client_network = NetworkManager(client_world, "localhost", 0)
client_network.connect_to("localhost", 1200)

client_scene.messenger.add_subscriber("replicable_added", lambda p: print("Replicable created", p))
server_replicable.score = 15
server_replicable.struct = ManyVectors()
server_replicable.struct.a.x = 12
server_replicable.do_work(1, "JAMES")

client_network.send(True)
server_network.receive()
server_network.send(True)
client_network.receive()

struct = client_scene.replicables[0].struct
print(struct)