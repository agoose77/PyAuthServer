from .replicables import Camera
from .events import PlayerInputEvent, PhysicsTickEvent
from .physics import PhysicsSystem

from collections import Counter
from bge import logic, events, types
from network import( Netmodes, WorldInfo, Network, Replicable,
                     EventListener, ReplicableRegisteredEvent,
                     UpdateEvent, NetworkReceiveEvent, NetworkSendEvent)
from time import monotonic


class GameLoop(types.KX_PythonLogicLoop, EventListener):

    def __init__(self):
        super().__init__()

        self.tick_rate = logic.getLogicTicRate()
        self.use_tick_rate = logic.getUseFrameRate()

        self.animation_rate = logic.getAnimationTicRate()
        self.use_animation_rate = logic.getRestrictAnimationUpdates()

        self.last_time = self.get_time()
        self.last_animation_time = self.get_time()

        self.network_scene = logic.getSceneList()[0]

        self.network = self.create_network()
        self.physics_system = PhysicsSystem(self.physics_callback,
                                            self.apply_physics)

        self._last_sent = 0.0
        self._interval = 1 / 20

        self.listen_for_events()

        WorldInfo.physics = self.physics_system

        print("Network initialised")

    @ReplicableRegisteredEvent.global_listener
    def notify_registration(self, target):

        if isinstance(target, Camera):
            target.render_temporary(self.update_render)

    def apply_physics(self):
        self.update_scenegraph(self.get_time())

    def physics_callback(self, delta_time):
        self.update_physics(self.get_time(), delta_time)

    def update_scene(self, scene, current_time, delta_time):
        self.update_logic_bricks(current_time)

        if scene == self.network_scene:
            self.start_profile(logic.KX_ENGINE_DEBUG_MESSAGES)
            NetworkReceiveEvent.invoke()

            Replicable.update_graph()

            self.start_profile(logic.KX_ENGINE_DEBUG_LOGIC)

            if WorldInfo.netmode != Netmodes.server:
                PlayerInputEvent.invoke(delta_time)

            UpdateEvent.invoke(delta_time)

            Replicable.update_graph()

            self.start_profile(logic.KX_ENGINE_DEBUG_PHYSICS)

            PhysicsTickEvent.invoke(scene, delta_time)

            self.start_profile(logic.KX_ENGINE_DEBUG_MESSAGES)

            is_full_update = (current_time - self._last_sent) >= self._interval

            if is_full_update:
                self._last_sent = current_time

            NetworkSendEvent.invoke(is_full_update)

        else:
            self.start_profile(logic.KX_ENGINE_DEBUG_PHYSICS)
            self.update_physics(current_time, delta_time)

            self.start_profile(logic.KX_ENGINE_DEBUG_SCENEGRAPH)
            self.update_scenegraph(current_time)

    def update_loop(self):

        while not self.check_quit():
            start_time = current_time = self.get_time()
            delta_time = current_time - self.last_time

            # If this is too early, skip frame
            if self.use_tick_rate and delta_time < (1 / self.tick_rate):
                self.start_profile(logic.KX_ENGINE_DEBUG_OUTSIDE)
                continue

            # Update IO events from Blender
            self.update_blender()

            for scene in logic.getSceneList():
                current_time = self.get_time()

                self.set_current_scene(scene)
                self.update_scene(scene, current_time, delta_time)

            # End of frame updates
            self.start_profile(logic.KX_ENGINE_DEBUG_SERVICES)
            self.update_keyboard()
            self.update_mouse()
            self.update_scenes()

            self.start_profile(logic.KX_ENGINE_DEBUG_RASTERIZER)
            self.update_render()

            self.start_profile(logic.KX_ENGINE_DEBUG_OUTSIDE)
            self.last_time = start_time

    def main(self):
        self.__init__()

        try:
            self.update_loop()

        except Exception as err:
            raise

        finally:
            self.network.stop()

"""
@todo: add level loading support
@todo load static actors
@todo: create AI controller
@todo: create Animation struct"""


class ServerGameLoop(GameLoop):

    def create_network(self):
        WorldInfo.netmode = Netmodes.server
        return Network("", 1200)


class ClientGameLoop(GameLoop):

    def create_network(self):
        WorldInfo.netmode = Netmodes.client
        return Network("localhost", 0)
