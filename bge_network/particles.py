from network.signals import SignalListener

from .object_types import create_object, BGEPhysicsObject


__all__ = ['Particle']


class Particle(BGEPhysicsObject, SignalListener):

    entity_name = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        game_object = create_object(self.__class__.entity_name)
        self.register(game_object)

        self.on_initialised()

    def on_initialised(self):
        pass

    def delete(self):
        super().delete()
        self.unregister_signals()
