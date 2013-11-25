from bge_network import ClientGameLoop, Camera, WorldInfo

from replicables import *
from client_ui import BGESystem


class Client(ClientGameLoop):

    def update_loop(self):
        self.ui_system = BGESystem()
        self.ui_system.connect_panel.connecter = self.new_connection

        super().update_loop()

    def update_scene(self, scene, current_time, delta_time):
        super().update_scene(scene, current_time, delta_time)

        if scene == self.network_scene:
            self.ui_system.update(delta_time)

    def new_connection(self, addr, port):
        conn = self.network.connect_to((addr, port))
