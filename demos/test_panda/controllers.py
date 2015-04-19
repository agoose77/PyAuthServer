from network.descriptors import TypeFlag
from network.rpc import Pointer
from network.enums import Netmodes
from network.world_info import WorldInfo

from game_system.controllers import PlayerPawnController
from game_system.inputs import InputContext


class TestPandaPlayerController(PlayerPawnController):
    input_context = InputContext(buttons=["left", "right", "up", "down"])

    def server_handle_inputs(self, move_id: TypeFlag(int, max_value=WorldInfo.MAXIMUM_TICK),
                             recent_states: TypeFlag(list, element_flag=TypeFlag(
                                 Pointer("input_context.network.struct_cls")))) -> Netmodes.server:
        """Handle remote client inputs

        :param move_id: unique ID of move
        :param recent_states: list of recent input states
        """
        super().server_handle_inputs(move_id, recent_states)

        try:
            state, move_id = next(self.buffer)
        except StopIteration:
            pass

        print(state, move_id)