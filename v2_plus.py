from network.world import World
from network.enums import Netmodes, Roles
from network.replication import Serialisable
from network.network import NetworkManager


from game_system.entity import Entity, MeshComponent, TransformComponent


class Rules:

    def pre_initialise(self, connection_info):
        pass

    def post_initialise(self, replication_manager, root_replicables):
        world = replication_manager.world
        scene = world.scenes["Scene"]

        # replicable = scene.add_replicable(Replicable2)
        # root_replicables.add(replicable)

    def is_relevant(self, replicable):
        return True


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


server_world = World(Netmodes.server)
server_world.rules = Rules()
server_network = NetworkManager(server_world, "localhost", 1200)

server_scene = server_world.add_scene("Scene")
server_replicable = server_scene.add_replicable(SomeEntity)
server_replicable.score = 100

from game_system.main_loop import FixedTimeStepManager
game_loop = FixedTimeStepManager()


def main():
    i = 0
    while True:
        server_network.receive()
        server_world.tick()
        server_network.send(not i % 3)
        i += 1
        dt = yield

loop = main()
next(loop)

game_loop.on_step = loop.send
game_loop.delegate()
