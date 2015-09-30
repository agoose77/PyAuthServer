from network_2.world import World
from network_2.replicable import Replicable


class Replicable2(Replicable):
    pass


class Network:

    def __init__(self, world):
        self.world = world

    def receive(self):
        pass

    def send(self):
        pass


world = World()
scene = world.add_scene("Scene")
replicable = scene.add_replicable("Replicable2")

