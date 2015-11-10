from network.enums import Netmodes
from network.world import World as _World

from .timers import TimerManager


class World(_World):

    def __init__(self, netmode, tick_rate, root_filepath):
        super().__init__(netmode)

        self.root_filepath = root_filepath
        self.timer_manager = TimerManager()

        self._tick_rate = tick_rate
        self._current_tick = 0

        if netmode == Netmodes.client:
            self.input_manager = self._create_input_manager()

        else:
            self.input_manager = None

    @property
    def current_tick(self):
        return self._current_tick

    @property
    def tick_rate(self):
        return self._tick_rate

    def _create_input_manager(self):
        raise NotImplementedError

    def _on_tick(self):
        self.timer_manager.update(1 / self._tick_rate)

        for scene in self.scenes.values():
            scene.tick()

    def tick(self):
        if self.netmode == Netmodes.client:
            self.input_manager.tick()

        self.messenger.send("tick")
        self._on_tick()
        self.messenger.send("post_tick")

        self._current_tick += 1
