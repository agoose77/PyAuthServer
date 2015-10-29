from network.world import World as _World


class World(_World):

    def __init__(self, netmode, tick_rate, root_filepath):
        super().__init__(netmode)

        self.tick_rate = tick_rate
        self.root_filepath = root_filepath