from bge_network.gameloop import ClientGameLoop
from bge_network.resources import ResourceManager

from .client_ui import FPSSystem
from .signals import ConnectToSignal

from bge import logic

ResourceManager.data_path = logic.expandPath("//data")


class Client(ClientGameLoop):

    def create_network(self):
        self.ui_system = FPSSystem()

        return super().create_network()

    @ConnectToSignal.global_listener
    def new_connection(self, addr, port):
        self.network_system.connect_to((addr, port))
