from collections import namedtuple

__all__ = ['Animation']


_Animation = namedtuple("Animation", "name start end layer priority \
                       blend mode weight speed blend_mode playing_callback")


class Animation(_Animation):

    @property
    def playing(self):
        return self.playing_callback()
