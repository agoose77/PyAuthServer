from .coordinates import Vector
from .enums import ListenerType

__all__ = ['InputState']


class InputState:
    """Interface to input handlers"""

    def __init__(self):
        self.buttons = {}
        self.ranges = {}