from collections import defaultdict
from contextlib import contextmanager


class ProtectedInstance:

    _is_allowed_creation = False
    creation_path_name = ""

    @classmethod
    @contextmanager
    def _allow_creation(cls):
        is_allowed, cls._is_allowed_creation = cls._is_allowed_creation, True
        yield
        cls._is_allowed_creation = is_allowed

    def __new__(cls, *args, **kwargs):
        if not cls._is_allowed_creation:
            raise RuntimeError("Must instantiate '{}' from '{}'"
            .format(cls.__name__, cls.creation_path_name))

        return super().__new__(cls)


class NamedSubclassTracker(type):

    def __new__(metacls, name, bases, namespace):
        cls = super().__new__(metacls, name, bases, namespace)

        try:
            subclasses = cls.subclasses

        except AttributeError:
            subclasses = cls.subclasses = {}

        subclasses[name] = cls
        return cls


class UniqueIDPool:

    def __init__(self, bound):
        self.bound = bound
        self._id_set = set(range(bound))

    def retire(self, unique_id):
        self._id_set.add(unique_id)

    def take(self):
        return self._id_set.pop()


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


class Scene(ProtectedInstance):

    def __init__(self, world, name):
        self.world = world
        self.name = name

        self.messenger = MessagePasser()
        self.replicables = {}

        self._unique_ids = UniqueIDPool(255)

    def add_replicable(self, cls_name, unique_id=None):
        replicable_cls = Replicable.subclasses[cls_name]

        if unique_id is None:
            unique_id = self._unique_ids.take()

        with Replicable._allow_creation():
            replicable = replicable_cls(scene, unique_id)

        self.replicables[unique_id] = replicable
        self.messenger.send("replicable_added", replicable)

        return replicable

    def remove_replicable(self, replicable):
        self.messenger.send("replicable_removed", replicable)

        unique_id, replicable.unique_id = replicable.unique_id, None
        self.replicables.pop(unique_id)
        self._unique_ids.retire(unique_id)

    def __repr__(self):
        return "<'{}' scene>".format(self.name)


class Replicable(ProtectedInstance, metaclass=NamedSubclassTracker):

    def __init__(self, scene, identifier):
        self.scene = scene
        self.identifier = identifier

    def __repr__(self):
        return "<{}.{}::{} replicable>".format(
            self.scene, self.__class__.__name__, self.identifier)


class MessagePasser:

    def __init__(self):
        self._subscribers = defaultdict(list)

    def add_subscriber(self, message_id, callback):
        self._subscribers[message_id].append(callback)

    def remove_subscriber(self, message_id, callback):
        self._subscribers[message_id].pop(callback)

    def send(self, identifier, message):
        try:
            callbacks = self._subscribers[identifier]

        except KeyError:
            return

        for callbacks in callbacks:
            callbacks(message)


class MyObj(Replicable):

    def __init__(self, scene, identifier):
        super().__init__(scene, identifier)


world = World()
scene = world.add_scene("Scene")
replicable = scene.add_replicable("MyObj")

print(replicable)
