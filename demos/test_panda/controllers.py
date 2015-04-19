from network.descriptors import TypeFlag
from network.rpc import Pointer
from network.decorators import requires_netmode
from network.enums import Netmodes
from network.world_info import WorldInfo

from game_system.controllers import PlayerPawnController
from game_system.inputs import InputContext
from game_system.signals import LogicUpdateSignal


class TestPandaPlayerController(PlayerPawnController):
    input_context = InputContext(buttons=["left", "right", "up", "down"])

    @LogicUpdateSignal.on_global
    @requires_netmode(Netmodes.server)
    def server_update(self, delta_time):
        try:
            state, move_id = next(self.buffer)

        except StopIteration:
            pass

        buttons, ranges = state
