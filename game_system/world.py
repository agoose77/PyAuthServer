from network.world import World as _World


class World(_World):

    def __init__(self, netmode, tick_rate, root_filepath):
        super().__init__(netmode)

        self.root_filepath = root_filepath

        self._tick_rate = tick_rate
        self._current_tick = 0

    @property
    def current_tick(self):
        return self._current_tick

    @property
    def tick_rate(self):
        return self._tick_rate

    def tick(self):
        self._current_tick += 1

        super().tick()
