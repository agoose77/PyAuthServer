from bge_network import ClientLoop, Camera

from actors import *
from ui import BGESystem


class Client(ClientLoop):

    def create_ui(self):
        system = BGESystem()

        system.connect_panel.connecter = self.new_connection
        return system

    def new_connection(self, addr, port):
        conn = self.network.connect_to((addr, port))

    def create_network(self):
        network = super().create_network()

        return network
