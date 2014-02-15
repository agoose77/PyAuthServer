from .timer import Timer
from .physics_object import PhysicsObject

from network.signals import SignalListener


class Particle(PhysicsObject, SignalListener):

    lifespan = 10

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.on_initialised()

    def request_unregistration(self):
        self.on_unregistered()

        self.unregister_signals()
