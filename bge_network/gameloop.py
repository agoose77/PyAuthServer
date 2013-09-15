from .actors import Camera
from .events import PlayerInputEvent, PhysicsTickEvent, UpdateEvent
from .physics import PhysicsSystem

from bge import logic, events, types
from network import Netmodes, WorldInfo, Network, Replicable, EventListener, ReplicableRegisteredEvent, event


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

        self.ui_system = self.create_ui()

        WorldInfo.physics = self.physics_system

        print("Network initialised")

    @event(ReplicableRegisteredEvent, True)
    def notify_registration(self, context):

        if isinstance(context, Camera):
            context.render_temporary(self.update_render)

    def apply_physics(self):
        self.update_scenegraph(self.get_time())

    def physics_callback(self, delta_time):
        self.update_physics(self.get_time(), delta_time)

    def run(self):

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

                self.update_logic_bricks(current_time)

                if scene == self.network_scene:
                    self.start_profile(logic.KX_ENGINE_DEBUG_MESSAGES)
                    self.network.receive()

                    Replicable.update_graph()

                    self.start_profile(logic.KX_ENGINE_DEBUG_LOGIC)

                    if WorldInfo.netmode != Netmodes.server:
                        PlayerInputEvent.invoke(delta_time)

                    UpdateEvent.invoke(delta_time)

                    Replicable.update_graph()

                    self.start_profile(logic.KX_ENGINE_DEBUG_PHYSICS)

                    PhysicsTickEvent.invoke(scene, delta_time)

                    if self.ui_system is not None:
                        self.ui_system.update(delta_time)

                else:
                    self.start_profile(logic.KX_ENGINE_DEBUG_PHYSICS)
                    self.update_physics(current_time, delta_time)

                    self.start_profile(logic.KX_ENGINE_DEBUG_SCENEGRAPH)
                    self.update_scenegraph(current_time)

                if scene == self.network_scene:
                    self.start_profile(logic.KX_ENGINE_DEBUG_MESSAGES)
                    self.network.send()

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
            self.run()

        except Exception as err:
            raise

        finally:
            self.network.stop()

"""
@todo: add level loading support
@todo load static actors
@todo: create AI controller
@todo: create Animation struct"""


class ServerLoop(GameLoop):

    def create_network(self):
        WorldInfo.netmode = Netmodes.server
        return Network("", 1200)


class ClientLoop(GameLoop):

    def create_network(self):
        WorldInfo.netmode = Netmodes.client
        return Network("localhost", 0)
