from network.replicable import Replicable
from network.decorators import simulated, requires_netmode
from network.descriptors import Attribute, TypeFlag
from network.enums import Netmodes, Roles
from network.world_info import WorldInfo

from .timer import Timer
from .signals import TimerUpdateSignal

from math import floor


class Clock(Replicable):

    roles = Attribute(Roles(Roles.authority, Roles.autonomous_proxy))

    def on_initialised(self):
        super().on_initialised()

        self.elapsed = 0.0

        self.on_server_initialised()
        self.on_client_initialised()

    @requires_netmode(Netmodes.client)
    def on_client_initialised(self):
        self.nudge_interval = 0.1
        self.nudge_factor = 0.8

    @requires_netmode(Netmodes.server)
    def on_server_initialised(self):
        self.poll_timer = Timer(2, repeat=True)
        self.poll_timer.on_target = self.server_send_clock

    def server_send_clock(self):
        self._server_send_clock(self.elapsed)

    def _server_send_clock(self, elapsed: TypeFlag(float)) -> Netmodes.client:
        controller = self.owner
        if controller is None:
            return

        info = controller.info

        # Find difference between local and remote time
        difference = self.elapsed - elapsed - info.ping
        if abs(difference) < self.nudge_interval:
            return

        self.elapsed -= difference * self.nudge_factor

    @property
    def tick(self):
        return floor(self.elapsed * WorldInfo.tick_rate)

    @property
    def sync_interval(self):
        return self.poll_timer.end

    @sync_interval.setter
    def sync_interval(self, value):
        self.poll_timer.end = value

    @TimerUpdateSignal.on_global
    @simulated
    def update(self, delta_time):
        self.elapsed += delta_time