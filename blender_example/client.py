from bge_network import ClientLoop, Camera, InstanceNotifier

from actors import *
from ui import BGESystem


class Client(ClientLoop):

    def create_ui(self):
        system = BGESystem()

        system.connect_panel.connecter = self.new_connection
        return system

    def on_connected(self):
        self.ui_system.connect_panel.visible = False

    def new_connection(self, addr, port):
        cb = self.ui_system.connect_panel.on_error
        conn = self.network.connect_to((addr, port), on_error=cb,
                                       on_connected=self.on_connected,
                                       on_timeout=cb)

    def create_network(self):
        network = super().create_network()

        return network
