from game_system.signals import LogicUpdateSignal

from bge_game_system.particles import Particle

__all__ = ["TracerParticle"]


class TracerParticle(Particle):
    entity_name = "Trace"

    def on_initialised(self):
        super().on_initialised()

        self.lifespan = 0.5
        self.scale = self.object.localScale.copy()

    @LogicUpdateSignal.global_listener
    def update(self, delta_time):
        self.object.localScale = self.scale * (1 - self._timer.progress) ** 2