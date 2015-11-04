from collections import OrderedDict

from .scene import Scene
from .messages import MessagePasser


class World:

    scene_class = Scene

    def __init__(self, netmode):
        self.scenes = OrderedDict()
        self.messenger = MessagePasser()
        self.netmode = netmode

        self.rules = None

    def add_scene(self, name):
        if name in self.scenes:
            raise ValueError("Scene with name '{}' already exists".format(name))

        with Scene._grant_authority():
            scene = self.__class__.scene_class(self, name)

        self.scenes[name] = scene
        self.messenger.send("scene_added", scene)

        return scene

    def remove_scene(self, scene):
        with Scene._grant_authority():
            scene.on_destroyed()

        self.scenes.pop(scene.name)
        self.messenger.send("scene_removed", scene)
