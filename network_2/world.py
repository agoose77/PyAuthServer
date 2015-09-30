from .scene import Scene
from .messages import MessagePasser


class World:

    def __init__(self):
        self.scenes = {}
        self.messenger = MessagePasser()

    def add_scene(self, name):
        if name in self.scenes:
            raise ValueError("Scene with name '{}' already exists".format(name))

        with Scene._allow_creation():
            scene = Scene(self, name)

        self.scenes[name] = scene
        self.messenger.send("scene_added", scene)

        return scene

    def remove_scene(self, scene):
        self.messenger.send("scene_removed", scene)
        self.scenes.pop(scene.name)
