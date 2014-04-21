from network.signals import SignalListener

from .physics_object import PhysicsObject


__all__ = ['Particle']


class Particle(PhysicsObject, SignalListener):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.on_initialised()

    def request_unregistration(self):
        self.on_unregistered()

        self.unregister_signals()
