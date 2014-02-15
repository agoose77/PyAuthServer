from ui import Panel, ConsoleRenderer, System, TableRenderer

from matchmaker import Matchmaker
from bge_network import (ConnectionErrorSignal, ConnectionSuccessSignal,
                     SignalListener, WorldInfo, ManualTimer)
from signals import ConsoleMessage
from datetime import datetime

import bge
import bgui

CENTERY = bgui.BGUI_DEFAULT | bgui.BGUI_CENTERY
CENTERX = bgui.BGUI_DEFAULT | bgui.BGUI_CENTERX
CENTERED = bgui.BGUI_DEFAULT | bgui.BGUI_CENTERED


class StatsPanel(Panel, SignalListener):

    def __init__(self, system):
        super().__init__(system, "Connect")

        self.connecter = None
        self.aspect = bge.render.getWindowWidth() / bge.render.getWindowHeight()

        self.center_column = bgui.Frame(parent=self, name="center",
                                        size=[0.8, 0.8], options=CENTERED,
                                        sub_theme="ContentBox")

        self.connect_label = bgui.Label(parent=self.center_column,
                                        name="label", pos=[0.0, 0.025],
                                        text="Connection Wizard",
                                        options=CENTERX, sub_theme="Title")

        # IP input
        self.connection_row = bgui.Frame(parent=self.center_column,
                                         name="connection_frame",
                                         size=[0.8, 0.08], pos=[0.0, 0.85],
                                         sub_theme="ContentRow",
                                         options=CENTERX)

        self.addr_group = bgui.Frame(parent=self.connection_row,
                                     name="addr_group", size=[0.70, 1.0],
                                     pos=[0.0, 0.5], options=CENTERY,
                                     sub_theme="RowGroup")
        self.port_group = bgui.Frame(parent=self.connection_row,
                                     name="port_group", size=[0.3, 1.0],
                                     pos=[0.7, 0.5], options=CENTERY,
                                     sub_theme="RowGroup")

        self.addr_label = bgui.Label(parent=self.addr_group, name="addr_label",
                                     text="IP Address:", options=CENTERY,
                                     pos=[0.05, 0.0])
        self.port_label = bgui.Label(parent=self.port_group, name="port_label",
                                     text="Port:", options=CENTERY,
                                     pos=[0.05, 0.0])

        self.addr_field = bgui.TextInput(parent=self.addr_group,
                                         name="addr_field", size=[0.6, 1.0],
                                         pos=[0.4, 0.0], options=CENTERY,
                                         text="localhost",
                                         allow_empty=False)
        self.port_field = bgui.TextInput(parent=self.port_group,
                                         name="port_field", size=[0.6, 1.0],
                                         pos=[0.4, 0.0], options=CENTERY,
                                         type=bgui.BGUI_INPUT_INTEGER,
                                         text="1200",
                                         allow_empty=False)

        # Allows input fields to accept input when not hovered
        self.connection_row.is_listener = True

        # Data input
        self.data_row = bgui.Frame(parent=self.center_column,
                                   name="data_frame", size=[0.8, 0.08],
                                   pos=[0.0, 0.77], sub_theme="ContentRow",
                                   options=CENTERX)

        self.error_msg_group = bgui.Frame(parent=self.data_row,
                                     name="error_msg_group", size=[0.3, 1.0],
                                     pos=[0.0, 0.5], options=CENTERY,
                                     sub_theme="RowGroup")

        self.error_msg_label = bgui.Label(parent=self.error_msg_group,
                                          name="error_status",
                                          text="Connection Information:",
                                          pos=[0.0, 0.0],
                                          options=CENTERED)

        self.error_group = bgui.Frame(parent=self.data_row,
                                     name="error_group", size=[0.7, 1.0],
                                     pos=[0.3, 0.5], options=CENTERY,
                                     sub_theme="RowGroup")

        self.connect_message = bgui.Label(parent=self.error_group,
                                          name="connect_status",
                                          text="",
                                          pos=[0.0, 0.0],
                                          options=CENTERED)

        self.server_controls = bgui.Frame(parent=self.center_column,
                                   name="server_controls", size=[0.8, 0.08],
                                   pos=[0.0, 0.69], sub_theme="ContentRow",
                                   options=CENTERX)

        self.refresh_group = bgui.Frame(parent=self.server_controls,
                                     name="refresh_group", size=[0.15, 1.0],
                                     pos=[0.0, 0.5], options=CENTERY,
                                     sub_theme="RowGroup")

        self.refresh_button = bgui.FrameButton(parent=self.refresh_group,
                                               name="refresh_button",
                                               text="Update", size=[1.0, 1.0],
                                               options=CENTERED)

        self.connect_group = bgui.Frame(parent=self.server_controls,
                                     name="connect_group", size=[0.15, 1.0],
                                     pos=[0.15, 0.5], options=CENTERY,
                                     sub_theme="RowGroup")

        self.connect_button = bgui.FrameButton(parent=self.connect_group,
                                               name="connect_button",
                                               text="Connect", size=[1.0, 1.0],
                                               options=CENTERED)

        self.match_group = bgui.Frame(parent=self.server_controls,
                                     name="match_group", size=[0.7, 1.0],
                                     pos=[0.3, 0.5], options=CENTERY,
                                     sub_theme="RowGroup")
        self.match_label = bgui.Label(parent=self.match_group, name="match_label",
                                     text="Matchmaker:", options=CENTERY,
                                     pos=[0.025, 0.0])
        self.match_field = bgui.TextInput(parent=self.match_group,
                                         name="match_field", size=[0.8, 1.0],
                                         pos=[0.2, 0.0], options=CENTERY,
                                         text="http://coldcinder.co.uk/networking/matchmaker",
                                         allow_empty=False)

        self.servers_list = bgui.Frame(parent=self.center_column,
                                   name="server_list", size=[0.8, 0.6],
                                   pos=[0.0, 0.09], sub_theme="ContentRow",
                                   options=CENTERX)
        self.servers = []
        self.server_headers = ["name",
                               "map",
                               "players",
                               "max_players",
                               ]

        self.matchmaker = Matchmaker("")

        self.servers_box = bgui.ListBox(parent=self.servers_list,
                                        name="servers",
                                        items=self.servers, padding=0.0,
                                        size=[1.0, 1.0],
                                        pos=[0.0, 0.0])
        self.servers_box.renderer = TableRenderer(self.servers_box,
                                              labels=self.server_headers)

        self.uses_mouse = True


class BGESystem(System):

    def __init__(self):
        super().__init__()

        self.stats_panel = StatsPanel(self)