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


class ITransformComponent:

    position = None
    rotation = None
    parent = None


class IPhysicsComponent:

    velocity = None
    angular = None
    collision_group = None
    collision_mask = None


class Actor(Replicable):
    components = ()


class ReplicableFactory:

    def __init__(self, environment):
        self._environment = environment

    def on_created_actor(self, replicable):
        # 1. Load config
        # 2. create components
        pass

    def on_destroyed_actor(self, replicable):
        pass

    def on_created(self, replicable):
        if isinstance(replicable, Actor):
            self.on_created_actor(replicable)

    def on_destroyed(self, replicable):
        if isinstance(replicable, Actor):
            self.on_destroyed_actor(replicable)


class Game:

    def __init__(self, world, network_manager):
        self.world = world
        self.network_manager = network_manager

        self.factories = {}

        world.messenger.add_subscriber("scene_added", self.configure_scene)

    def configure_scene(self, scene):
        self.factories[scene] = factory = ReplicableFactory('panda')

        scene.messenger.add_subscriber("replicable_created", factory.on_created)
        scene.messenger.add_subscriber("replicable_destroyed", factory.on_destroyed)


server_world = World(Netmodes.server)
server_world.rules = Rules()
server_network = NetworkManager(server_world, "localhost", 1200)
server_game = Game(server_world, server_network)

server_scene = server_world.add_scene("Scene")
server_replicable = server_scene.add_replicable(Replicable2)
server_actor = server_scene.add_replicable(Actor)

client_world = World(Netmodes.client)
client_network = NetworkManager(client_world, "localhost", 0)
client_game = Game(client_world, client_network)

client_scene = client_world.add_scene("Scene")
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