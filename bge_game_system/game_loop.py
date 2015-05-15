from collections import OrderedDict, namedtuple
from contextlib import contextmanager

from network.enums import Netmodes
from network.network import Network, UnreliableSocketWrapper
from network.replicable import Replicable
from network.signals import *
from network.world_info import WorldInfo

from game_system.signals import *
from game_system.timer import Timer
from game_system.entities import Camera
from game_system.game_loop import FixedTimeStepManager, OnExitUpdate

from .inputs import BGEInputManager
from .physics import BGEPhysicsSystem
from .definitions import BGEComponentLoader

from bge import types, logic


__all__ = ['GameLoop', 'Server', 'Client', 'RewindState']


RewindState = namedtuple("RewindState", "position rotation animations")

#TODO profile_category server to determine why slow
#TODO consider other means of sending past moves
#TODO Move away from un handled exceptions in protected (no-return) code
#TODO implement client-side extrapolation
#TODO implement raycast weapons
#TODO rename non-actor s


def for_non_patched_build():
    class FAKE_KX_PythonLogicLoop:

        def start_profile(self, p):
            pass

        def update_scenes(self):
            pass

        def update_animations(self, t):
            pass

        def check_quit(self):
            return logic.getExitKey() in logic.keyboard.active_events

        def update_physics(self, *a, **k):
            pass

        def update_scenegraph(self, t):
            pass

        def update_blender(self):
            pass

        def update_logic_bricks(self, t):
            logic.NextFrame()

        def update_render(self):
            pass

        def update_mouse(self):
            pass

        def update_keyboard(self):
            pass

        def set_current_scene(self, s):
            pass


    logic.getUseFrameRate = lambda: True
    logic.getRestrictAnimationUpdates = lambda: True
    logic.getAnimationTicRate = lambda: 24

    logic.KX_ENGINE_DEBUG_ANIMATIONS = 0
    logic.KX_ENGINE_DEBUG_LOGIC = 1
    logic.KX_ENGINE_DEBUG_MESSAGES = 2
    logic.KX_ENGINE_DEBUG_PHYSICS = 3
    logic.KX_ENGINE_DEBUG_RASTERIZER = 4
    logic.KX_ENGINE_DEBUG_SCENEGRAPH = 5
    logic.KX_ENGINE_DEBUG_SERVICES = 6

    types.KX_PythonLogicLoop = FAKE_KX_PythonLogicLoop


# If not patched, use lazy types
if not hasattr(types, "KX_PythonLogicLoop"):
    for_non_patched_build()


class GameLoop(types.KX_PythonLogicLoop, SignalListener, FixedTimeStepManager):

    allow_update_display = True

    def __init__(self):
        super().__init__()

        self.register_signals()

        WorldInfo.tick_rate = int(logic.getLogicTicRate())

        # Copy BGE data
        self.use_tick_rate = logic.getUseFrameRate()
        self.animation_rate = logic.getAnimationTicRate()
        self.use_animation_rate = logic.getRestrictAnimationUpdates()

        self.network_scene = next(iter(logic.getSceneList()))
        self.network_scene.post_draw = [self.render_callback]
        BGEComponentLoader.scene = self.network_scene

        # Create sub systems
        self.network_system = self.create_network()
        self.physics_system = BGEPhysicsSystem(self.physics_callback, self.scenegraph_callback)

        self.input_manager = BGEInputManager()

        # Timing information
        self.last_sent_time = 0
        self.current_time = 0

        self.network_tick_rate = 25
        self.metric_interval = 0.10

        # Profile information
        self._state = None

        self.profile_category = logic.KX_ENGINE_DEBUG_SERVICES
        self.pending_exit = False

        # Load world
        MapLoadedSignal.invoke()

        print("Network initialised")

    @contextmanager
    def profile_as(self, context_profile):
        """Restores original profile after context collapses

        :param context_profile: profile for this context
        """
        self._state, self.profile_category = self.profile_category, context_profile

        yield self._state

        self.profile_category = self._state

    @property
    def profile_category(self):
        """Return current profile category"""
        return self._profile

    @profile_category.setter
    def profile_category(self, value):
        """Set current profile category

        :param value: new profile category
        """
        self.start_profile(value)

        self._profile = value

    @ReplicableRegisteredSignal.on_global
    def notify_registered(self, target):
        """Signal on_context for replicable instantiation
        Listens for Camera creation to correct camera matrices

        :param target: replicable instance"""
        if isinstance(target, Camera):

            with target.active_context():
                self.update_render()

    def scenegraph_callback(self):
        """Callback for scenegraph update"""
        with self.profile_as(logic.KX_ENGINE_DEBUG_PHYSICS):
            self.update_scenegraph(self.current_time)

    def render_callback(self):
        """Callback for render update"""
        with self.profile_as(logic.KX_ENGINE_DEBUG_RASTERIZER):
            UIRenderSignal.invoke()

    def physics_callback(self, delta_time):
        """Callback for physics simulation

        :param delta_time: time to progress simulation"""
        with self.profile_as(logic.KX_ENGINE_DEBUG_PHYSICS):
            self.update_physics(self.current_time, delta_time)

    def update_network_scene(self, delta_time):
        self.profile_category = logic.KX_ENGINE_DEBUG_MESSAGES
        self.network_system.receive()

        # Update inputs
        self.input_manager.update()

        # Update Player Controller inputs for client
        if WorldInfo.netmode != Netmodes.server:
            PlayerInputSignal.invoke(delta_time, self.input_manager.state)

        # Update main logic (Replicable update)
        LogicUpdateSignal.invoke(delta_time)

        # Update Physics, which also handles Scene-graph
        self.profile_category = logic.KX_ENGINE_DEBUG_PHYSICS
        PhysicsTickSignal.invoke(delta_time)

        # Clean up following Physics update
        PostPhysicsSignal.invoke()

        # Update Animation system
        self.profile_category = logic.KX_ENGINE_DEBUG_ANIMATIONS
        self.update_animations(self.current_time)

        # Transmit new state to remote peer
        self.profile_category = logic.KX_ENGINE_DEBUG_MESSAGES
        is_full_update = ((self.current_time - self.last_sent_time) >= (1 / self.network_tick_rate))

        if is_full_update:
            self.last_sent_time = self.current_time

        self.network_system.send(is_full_update)

        network_metrics = self.network_system.metrics
        if network_metrics.sample_age >= self.metric_interval:
            network_metrics.reset_sample_window()

        # Update UI
        self.profile_category = logic.KX_ENGINE_DEBUG_RASTERIZER

        UIUpdateSignal.invoke(delta_time)

        # Update Timers
        self.profile_category = logic.KX_ENGINE_DEBUG_LOGIC

        TimerUpdateSignal.invoke(delta_time)

        # Handle this outside of usual update
        WorldInfo.update_clock(delta_time)

        # # Set mouse position
        # logic.mouse.position = tuple(MouseManager.position)
        # logic.mouse.visible = MouseManager.visible

    def update_scene(self, scene, delta_time):
        self.profile_category = logic.KX_ENGINE_DEBUG_LOGIC
        self.update_logic_bricks(self.current_time)

        if scene is self.network_scene:
            self.update_network_scene(delta_time)

        else:
            self.profile_category = logic.KX_ENGINE_DEBUG_PHYSICS
            self.update_physics(self.current_time, delta_time)

            self.profile_category = logic.KX_ENGINE_DEBUG_SCENEGRAPH
            self.update_scenegraph(self.current_time)

    def invoke_exit(self):
        self.pending_exit = True

    def on_step(self, delta_time):
        self.profile_category = logic.KX_ENGINE_DEBUG_SERVICES
        self.update_blender()

        # If an exit is requested
        if self.check_quit():
            self.invoke_exit()

        # If we are pending an exit
        if self.pending_exit:
            raise OnExitUpdate()

        # Update all scenes
        for scene in logic.getSceneList():
            self.set_current_scene(scene)

            self.update_scene(scene, delta_time)

        # End of frame updates
        self.profile_category = logic.KX_ENGINE_DEBUG_SERVICES

        self.update_keyboard()
        self.update_mouse()
        self.update_scenes()

        if self.allow_update_display and self.use_tick_rate:
            self.profile_category = logic.KX_ENGINE_DEBUG_RASTERIZER
            self.update_render()

        self.current_time += delta_time

    def on_update(self, delta_time):
        # Render as often as possible
        if self.allow_update_display and not self.use_tick_rate:
            self.profile = logic.KX_ENGINE_DEBUG_RASTERIZER
            self.update_render()

    def clean_up(self):
        GameExitSignal.invoke()
        Replicable.clear_graph()
        self.network_system.stop()

    def main(self):
        self.__init__()

        try:
            self.delegate()

        finally:
            self.clean_up()


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

    def on_step(self, delta_time):
        network = self.network_system
        if hasattr(network.socket, "update"):
            network.socket.update()

        super().on_step(delta_time)

    @staticmethod
    def create_network():
        network = Network("", 0)
        #network.socket = UnreliableSocketWrapper(network.socket)
        return network

    @ConnectToSignal.on_global
    def new_connection(self, address, port):
        self.network_system.connect_to((address, port))