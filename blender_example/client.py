from bge_network import ClientGameLoop, Camera, WorldInfo

from replicables import *
from client_ui import BGESystem
from signals import ConnectToSignal

from bge import logic


class Client(ClientGameLoop):

    def update_loop(self):
        self.ui_system = BGESystem()

        super().update_loop()

    def update_scene(self, scene, current_time, delta_time):
        super().update_scene(scene, current_time, delta_time)

        if scene == self.network_scene:
            self.start_profile(logic.KX_ENGINE_DEBUG_LOGIC)
            self.ui_system.update(delta_time)

    @ConnectToSignal.global_listener
    def new_connection(self, addr, port):
        self.network.connect_to((addr, port))
