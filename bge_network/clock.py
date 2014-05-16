from network.decorators import requires_netmode
from network.enums import Netmodes
from network.descriptors import Attribute, TypeFlag
from network.replicable import Replicable
from network.world_info import WorldInfo

from .timer import Timer
from .utilities import lerp

TICK_FLAG = TypeFlag(int, max_value=WorldInfo._MAXIMUM_TICK)


class PlayerClock(Replicable):

    def on_initialised(self):
        self.ping_influence_factor = 0.8

       # self.ping_timer = Timer(1.0, repeat=True)
       # self.ping_timer.on_target = self.server_calculate_ping

    def _client_adjust_clock(self, ticks: TICK_FLAG, forward: TypeFlag(bool)) -> Netmodes.client:

        self.server_remove_lock("clock")
        time_delta = ticks / WorldInfo.tick_rate * (2 * forward - 1)
        WorldInfo.elapsed += time_delta

    def _client_reply_ping_request(self, tick: TICK_FLAG) -> Netmodes.client:
        """Client RPC which invokes server response
        """
        self._server_deduce_ping(tick)

    def _server_deduce_ping(self, tick: TICK_FLAG) -> Netmodes.server:
        """Callback to determine ping for a client
        Called by client_reply_ping(tick)
        Unlocks the ping synchronisation lock

        :param tick: tick from client reply replicated function
        """
        tick_delta = (WorldInfo.tick - tick)
        round_trip_time = tick_delta / WorldInfo.tick_rate

        self.info.ping = lerp(self.info.ping, round_trip_time, self.ping_influence_factor)
        self.server_remove_lock("ping")

    @requires_netmode(Netmodes.server)
    def server_calculate_ping(self):
        """Start estimating the ping from the client"""
        if not self.is_locked("ping"):
            self._client_reply_ping_request(WorldInfo.tick)
            self.server_add_lock("ping")

    @requires_netmode(Netmodes.server)
    def server_check_clock(self, move_tick):
        """Determines if client clock is far from the server clock,
        if this is the case, ask the client to adjust the clock

        :param move_tick: tick move
        """
        tick_difference = abs(WorldInfo.tick - move_tick)

        time_offset = (tick_difference * WorldInfo.tick_rate)
        if time_offset > self.clock_ignore_time and not self.is_locked("clock"):
            self.server_add_lock("clock")
            self._client_adjust_clock(tick_difference, forward=(WorldInfo.tick > move_tick))