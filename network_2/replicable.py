from .factory import ProtectedInstance, NamedSubclassTracker


class Replicable(ProtectedInstance, metaclass=NamedSubclassTracker):

    def __init__(self, scene, identifier):
        self.scene = scene
        self.identifier = identifier

    def __repr__(self):
        return "<{}.{}::{} replicable>".format(
            self.scene, self.__class__.__name__, self.identifier)

