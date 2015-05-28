from .decorators import simulated
from .descriptors import Attribute
from .enums import Roles, Netmodes
from .replicable import Replicable

__all__ = ['_WorldInfo', 'WorldInfo']


class _WorldInfo(Replicable):
    """Holds info about game state"""

    MAXIMUM_TICK = (2 ** 32 - 1)
    _ID = 255

    roles = Attribute(Roles(Roles.authority, Roles.simulated_proxy))

    elapsed = Attribute(0.0, complain=False)
    tick_rate = Attribute(60, complain=True, notify=True)

    netmode = Netmodes.server
    rules = None

    def on_initialised(self):
        self.always_relevant = True

    def conditions(self, is_owner, is_complain, is_initial):
        yield from super().conditions(is_owner, is_complain, is_initial)

        if is_initial:
            yield "elapsed"

        if is_complain:
            yield "tick_rate"

    @property
    def tick(self):
        """:returns: current simulation tick"""
        return self.to_ticks(self.elapsed)

    @simulated
    def to_ticks(self, delta_time):
        """Converts delta time into approximate number of ticks

        :param delta_time: time in seconds
        :returns: ticks according to current tick rate
        """
        return round(delta_time * self.tick_rate)

    @simulated
    def update_clock(self, delta_time):
        """Update internal clock

        :param delta_time: delta time since last simulation tick
        """
        self.elapsed += delta_time


WorldInfo = _WorldInfo(_WorldInfo._ID)