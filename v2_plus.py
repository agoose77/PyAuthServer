from network_2.world import World
from network_2.replicable import Replicable
from network_2.enums import Netmodes, Roles
from network_2.replication import Serialisable
from network_2.network import NetworkManager
from network_2.struct import Struct


class Replicable2(Replicable):
    score = Serialisable(data_type=int, flag_on_assignment=True)
    roles = Serialisable(Roles(Roles.authority, Roles.simulated_proxy))

    def can_replicate(self, is_owner, is_initial):
        yield "score"
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
# How to make this one-click importable without manually typing / hacky global lookups


from bge_game_system.entity import BGEConfigurationManager


# from bge import logic
from os import path, getcwd


class ResourceManager:

    def __init__(self, root_path):
        self._root_path = root_path

    def open(self, file_path, mode='r'):
        full_path = path.join(self._root_path, file_path)
        return open(full_path, mode)



from game_system.entity import Entity
from functools import partial

def call_if_is_entity(replicable, func):
    if isinstance(replicable, Entity):
        func(replicable)


class Rep3(Replicable2, Entity):
    pass


class Game:

    def __init__(self, world, network_manager):
        self.world = world
        self.network_manager = network_manager

        self.entity_configuration_managers = {}

        world.messenger.add_subscriber("scene_added", self.configure_scene)

        self._root = path.join(getcwd(), "demos/v2/data")

    def configure_scene(self, scene):
        bge_scene = "SomeScene"#logic.getSceneList()[scene.name]

        scene_resource_manager = ResourceManager(path.join(self._root, scene.name))
        self.entity_configuration_managers[scene] = configuration = BGEConfigurationManager(bge_scene,
                                                                                            scene_resource_manager)
        configure = partial(call_if_is_entity, func=configuration.configure_entity)
        deconfigure = partial(call_if_is_entity, func=configuration.deconfigure_entity)

        scene.messenger.add_subscriber("replicable_created", configure)
        scene.messenger.add_subscriber("replicable_destroyed", deconfigure)


server_world = World(Netmodes.server)
server_world.rules = Rules()
server_network = NetworkManager(server_world, "localhost", 1200)
server_game = Game(server_world, server_network)

server_scene = server_world.add_scene("Scene")
server_replicable = server_scene.add_replicable(Replicable2)
server_actor = server_scene.add_replicable(Rep3)

client_world = World(Netmodes.client)
client_network = NetworkManager(client_world, "localhost", 0)
client_game = Game(client_world, client_network)

client_scene = client_world.add_scene("Scene")
client_network.connect_to("localhost", 1200)

client_scene.messenger.add_subscriber("replicable_added", lambda p: print("Replicable created", p))
server_replicable.score = 15
server_replicable.do_work(1, "JAMES")

client_network.send(True)
server_network.receive()
server_network.send(True)
client_network.receive()
