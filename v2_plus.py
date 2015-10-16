from network.world import World
from network.replicable import Replicable
from network.enums import Netmodes, Roles
from network.replication import Serialisable
from network.network import NetworkManager
from network.struct import Struct


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

        # replicable = scene.add_replicable(Replicable2)
        # root_replicables.add(replicable)

    def is_relevant(self, replicable):
        print(replicable, "REL?")
        return True


# TODO: enable actor-like replicables cross-platform
# How do resources fit into world-paradigm? (Environment?)
#


class Game:

    def __init__(self, world, network_manager):
        self.world = world
        self.network_manager = network_manager

        self.factories = {}

        world.messenger.add_subscriber("scene_added", self.configure_scene)

    def configure_scene(self, scene):
        pass

from game_system.entity import Entity, MeshComponent, TransformComponent


class SomeEntity(Entity):

    mesh = MeshComponent("player")
    transform = TransformComponent(position=(0, 0, 0), orientation=(0, 0, 0))

    def can_replicate(self, is_owner, is_initial):
        yield from super().can_replicate(is_owner, is_initial)
        yield "score"

    def on_replicated(self, name):
        print(name, "replicated!")

    def on_score_replicated(self):
        print(self.score, "Updated")

    score = Serialisable(data_type=int, notify_on_replicated=True)
    roles = Serialisable(Roles(Roles.authority, Roles.simulated_proxy))


from bge_game_system.game import Game

server_world = World(Netmodes.server)
server_world.rules = Rules()
server_network = NetworkManager(server_world, "localhost", 1200)
server_game = Game(server_world, server_network)

server_scene = server_world.add_scene("Scene")
server_replicable = server_scene.add_replicable(SomeEntity)
server_replicable.score = 100

client_world = World(Netmodes.client)
client_network = NetworkManager(client_world, "localhost", 0)
client_game = Game(client_world, client_network)

client_scene = client_world.add_scene("Scene")
client_network.connect_to("localhost", 1200)

client_scene.messenger.add_subscriber("replicable_added", lambda p: print("Replicable created", p))

client_network.send(True)
server_network.receive()
server_network.send(True)
client_network.receive()
