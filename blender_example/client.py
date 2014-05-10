from bge_network.gameloop import ClientGameLoop
from bge_network.resources import ResourceManager

from .client_ui import BGESystem
from .signals import ConnectToSignal

from bge import logic

ResourceManager.data_path = logic.expandPath("//data")


class Client(ClientGameLoop):

    def create_network(self):
        self.ui_system = BGESystem()

        return super().create_network()

    def update_scene(self, scene, current_time, delta_time):
        super().update_scene(scene, current_time, delta_time)

        if scene == self.network_scene:
            self.start_profile(logic.KX_ENGINE_DEBUG_LOGIC)
            self.ui_system.update(delta_time)

    @ConnectToSignal.global_listener
    def new_connection(self, addr, port):
        self.network_system.connect_to((addr, port))
