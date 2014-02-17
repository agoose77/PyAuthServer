from .replicables import Camera
from .signals import (PlayerInputSignal, PhysicsTickSignal,
                      MapLoadedSignal, GameExitSignal,
                      PostPhysicsSignal)
from .physics import PhysicsSystem

from collections import Counter
from bge import logic, events, types
from network import (Netmodes, WorldInfo, Network, Replicable,
                     SignalListener, ReplicableRegisteredSignal,
                     UpdateSignal, Signal)
from time import monotonic


class GameLoop(types.KX_PythonLogicLoop, SignalListener):

    def __init__(self):
        super().__init__()

        WorldInfo.tick_rate = int(logic.getLogicTicRate())
        print("Set tick rate", WorldInfo.tick_rate)

        self.use_tick_rate = logic.getUseFrameRate()

        self.animation_rate = logic.getAnimationTicRate()
        self.use_animation_rate = logic.getRestrictAnimationUpdates()

        self.network_scene = logic.getSceneList()[0]

        self.network = self.create_network()
        self.physics_system = PhysicsSystem(self.physics_callback,
                                            self.apply_physics)

        self.current_time = 0.0

        self._last_sent = 0.0
        self._interval = 1 / 25
        self._profile = None

        Signal.update_graph()

        MapLoadedSignal.invoke()

        print("Network initialised")

    @ReplicableRegisteredSignal.global_listener
    def notify_registration(self, target):
        if isinstance(target, Camera):
            target.render_temporary(self.update_render)

    def start_profile(self, *args, **kwargs):
        self._profile = args, kwargs
        super().start_profile(*args, **kwargs)

    def apply_physics(self):
        _profile = self._profile
        self.start_profile(logic.KX_ENGINE_DEBUG_PHYSICS)
        self.update_scenegraph(self.current_time)
        self.start_profile(*_profile[0], **_profile[1])

    def physics_callback(self, delta_time):
        _profile = self._profile
        self.start_profile(logic.KX_ENGINE_DEBUG_PHYSICS)
        self.update_physics(self.current_time, delta_time)
        self.start_profile(*_profile[0], **_profile[1])

    def update_scene(self, scene, current_time, delta_time):
        self.start_profile(logic.KX_ENGINE_DEBUG_LOGIC)
        self.update_logic_bricks(current_time)

        if scene == self.network_scene:
            Signal.update_graph()

            self.start_profile(logic.KX_ENGINE_DEBUG_MESSAGES)
            self.network.receive()
            Signal.update_graph()

            self.start_profile(logic.KX_ENGINE_DEBUG_LOGIC)
            Replicable.update_graph()
            Signal.update_graph()

            if WorldInfo.netmode != Netmodes.server:
                PlayerInputSignal.invoke(delta_time)

            UpdateSignal.invoke(delta_time)

            Replicable.update_graph()
            Signal.update_graph()

            self.start_profile(logic.KX_ENGINE_DEBUG_PHYSICS)
            PhysicsTickSignal.invoke(scene, delta_time)

            PostPhysicsSignal.invoke()

            Replicable.update_graph()
            Signal.update_graph()

            self.start_profile(logic.KX_ENGINE_DEBUG_ANIMATIONS)
            self.update_animations(current_time)

            self.start_profile(logic.KX_ENGINE_DEBUG_MESSAGES)
            is_full_update = (current_time - self._last_sent) >= self._interval

            if is_full_update:
                self._last_sent = current_time

            self.network.send(is_full_update)

        else:
            self.start_profile(logic.KX_ENGINE_DEBUG_PHYSICS)
            self.update_physics(current_time, delta_time)

            self.start_profile(logic.KX_ENGINE_DEBUG_SCENEGRAPH)
            self.update_scenegraph(current_time)

    def update_loop(self):
        last_time = self.get_time()

        accumulator = 0.0

        # Fixed timestep
        while not self.check_quit():
            current_time = self.get_time()

            step_time = 1 / WorldInfo.tick_rate

            delta_time = current_time - last_time
            last_time = current_time

            if (delta_time > 0.25):
                delta_time = 0.25

            accumulator += delta_time

            # Whilst we have enough time in the buffer
            while (accumulator >= step_time):
                # Update IO events from Blender
                self.start_profile(logic.KX_ENGINE_DEBUG_SERVICES)
                self.update_blender()

                WorldInfo.update_clock(step_time)

                # Update all scenes
                for scene in logic.getSceneList():
                    self.set_current_scene(scene)
                    self.update_scene(scene, current_time, step_time)

                # End of frame updates
                self.start_profile(logic.KX_ENGINE_DEBUG_SERVICES)

                self.update_keyboard()
                self.update_mouse()
                self.update_scenes()

                if self.use_tick_rate:
                    self.update_render()

                self.current_time += step_time
                accumulator -= step_time

            self.start_profile(logic.KX_ENGINE_DEBUG_RASTERIZER)

            if not self.use_tick_rate:
                self.update_render()

            self.start_profile(logic.KX_ENGINE_DEBUG_OUTSIDE)

    def clean_up(self):
        GameExitSignal.invoke()

        for replicable in Replicable:
            replicable.request_unregistration()
        Replicable.update_graph()

    def main(self):
        self.__init__()

        try:
            self.update_loop()

        except Exception as err:
            raise

        finally:
            self.clean_up()
            self.network.stop()

"""
@todo: add level loading support
"""


class ServerGameLoop(GameLoop):

    def create_network(self):
        WorldInfo.netmode = Netmodes.server

        return Network("", 1200)


class ClientGameLoop(GameLoop):

    def create_network(self):
        WorldInfo.netmode = Netmodes.client

        return Network("", 0)
