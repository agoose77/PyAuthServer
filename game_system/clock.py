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

        self.on_server_initialised()
        self.on_client_initialised()

    @requires_netmode(Netmodes.client)
    def on_client_initialised(self):
        self.nudge_minimum = 0.05
        self.nudge_maximum = 0.4
        self.nudge_factor = 0.8

        self.estimated_elapsed_server = 0.0

    @requires_netmode(Netmodes.server)
    def on_server_initialised(self):
        self.poll_timer = Timer(1.0, repeat=True)
        self.poll_timer.on_target = self.server_send_clock

    def server_send_clock(self):
        self.client_update_clock(WorldInfo.elapsed)

    def client_update_clock(self, elapsed: TypeFlag(float)) -> Netmodes.client:
        controller = self.owner
        if controller is None:
            return

        info = controller.info

        # Find difference between local and remote time
        difference = self.estimated_elapsed_server - (elapsed + info.ping)
        abs_difference = abs(difference)

        if abs_difference < self.nudge_minimum:
            return

        if abs_difference > self.nudge_maximum:
            self.estimated_elapsed_server -= difference

        else:
            self.estimated_elapsed_server -= difference * self.nudge_factor

    @property
    def tick(self):
        return floor(self.estimated_elapsed_server * WorldInfo.tick_rate)

    @property
    def sync_interval(self):
        return self.poll_timer.end

    @sync_interval.setter
    def sync_interval(self, value):
        self.poll_timer.end = value

    @TimerUpdateSignal.on_global
    @simulated
    @requires_netmode(Netmodes.client)
    def update(self, delta_time):
        self.estimated_elapsed_server += delta_time