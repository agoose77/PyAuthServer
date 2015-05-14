from network.enums import Netmodes
from network.network import Network
from network.signals import SignalListener, Signal
from network.world_info import WorldInfo
from network.signals import DisconnectSignal
from network.replicable import Replicable

from game_system.timer import Timer
from game_system.signals import ConnectToSignal, TimerUpdateSignal, UIUpdateSignal, PlayerInputSignal, \
    LogicUpdateSignal, PhysicsTickSignal, PostPhysicsSignal
from game_system.game_loop import FixedTimeStepManager, OnExitUpdate
from game_system.enums import ButtonState, InputButtons

from panda_game_system.physics import PandaPhysicsSystem

from direct.showbase.ShowBase import ShowBase

from .inputs import PandaInputManager


class GameLoop(SignalListener, FixedTimeStepManager, ShowBase):

    def __init__(self):
        FixedTimeStepManager.__init__(self)
        ShowBase.__init__(self)

        self.register_signals()

        # Todo: Copy Panda data
        WorldInfo.tick_rate = 60
        self.use_tick_rate = True
        self.animation_rate = 24
        self.use_animation_rate = True

        # Create sub systems
        self.network_system = self.create_network()
        self.input_manager = PandaInputManager()
        self.physics_system = PandaPhysicsSystem()

        # Timing information
        self.last_sent_time = 0
        self.current_time = 0

        self.network_tick_rate = 25
        self.metric_interval = 0.10

        # Load world
        self.pending_exit = False

        print("Network initialised")

    def cleanup(self):
        self.destroy()

    def invoke_exit(self):
        self.pending_exit = True

    def on_step(self, delta_time):
        self.network_system.receive()

        # Update inputs
        base.taskMgr.step()
        self.input_manager.update()

        input_state = self.input_manager.state

        # Todo: allow this to be specified by game
        if input_state.buttons[InputButtons.ESCKEY] == ButtonState.pressed:
            self.invoke_exit()

        if self.pending_exit:
            raise OnExitUpdate()

        # Update Player Controller inputs for client
        if WorldInfo.netmode != Netmodes.server:
            PlayerInputSignal.invoke(delta_time, input_state)

        # Update main logic (Replicable update)
        LogicUpdateSignal.invoke(delta_time)

        # Update Physics, which also handles Scene-graph
        PhysicsTickSignal.invoke(delta_time)

        # Clean up following Physics update
        PostPhysicsSignal.invoke()

        # Transmit new state to remote peer
        is_full_update = ((self.current_time - self.last_sent_time) >= (1 / self.network_tick_rate))

        if is_full_update:
            self.last_sent_time = self.current_time

        self.network_system.send(is_full_update)

        network_metrics = self.network_system.metrics
        if network_metrics.sample_age >= self.metric_interval:
            network_metrics.reset_sample_window()

        # Update UI
        UIUpdateSignal.invoke(delta_time)

        # Update Timers
        TimerUpdateSignal.invoke(delta_time)

        # Handle this outside of usual update
        WorldInfo.update_clock(delta_time)
        self.current_time += delta_time


class Server(GameLoop):

    @staticmethod
    def create_network():
        return Network("", 1200)


class Client(GameLoop):

    graceful_exit_time_out = 0.6

    def invoke_exit(self):
        """Gracefully quit server"""
        quit_func = super().invoke_exit()
        # Try and quit gracefully
        DisconnectSignal.invoke(quit_func)
        # But include a time out
        timeout = Timer(self.graceful_exit_time_out)
        timeout.on_target = quit_func

    @staticmethod
    def create_network():
        return Network("", 0)

    @ConnectToSignal.on_global
    def new_connection(self, address, port):
        self.network_system.connect_to(address, port)