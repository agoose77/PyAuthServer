from ui import (Panel, ConsoleRenderer, System, TableRenderer,
                CENTERX, CENTERY, CENTERED)

from matchmaker import Matchmaker
from bge_network import (ConnectionErrorSignal, ConnectionSuccessSignal,
                     SignalListener, WorldInfo, ManualTimer, BroadcastMessage)
from signals import ConsoleMessage
from datetime import datetime

import bge
import bgui

import uuid
import copy


class ConnectPanel(Panel, SignalListener):

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

        #self.sprite = SpriteSequence(self.servers_box, "sprite", "C:/Users/Angus/workspace/ReplicationSystem/trunk/blender_example/themes/477.png",
                #                     length=20, loop=True,  size=[1, 1],  pos=[0, 0],
                 #                    relative_path=False)
        #self.sprite_timer = ManualTimer(target_value=1 / 20,
                                     #   repeat=True,
                                     #   on_target=self.sprite.next_frame)
        self.connect_button.on_click = self.do_connect
        self.refresh_button.on_click = self.do_refresh
        self.servers_box.on_select = self.on_select
        self.uses_mouse = True

        self.register_signals()

    def on_select(self, list_box, entry):
        data = dict(entry)

        self.addr_field.text = data['address']
        self.port_field.text = data['port']

    def do_refresh(self, button):
        self.matchmaker.url = self.match_field.text
        self.matchmaker.perform_query(self.evaluate_servers,
                                      self.matchmaker.server_query())

    def evaluate_servers(self, response):
        self.servers[:] = [tuple(entry.items()) for entry in response]
        self.connect_message.text = ("Refreshed Server List" if self.servers
                                    else "No Servers Found")

    def do_connect(self, button):
        if not callable(self.connecter):
            return

        self.connecter(self.addr_field.text, int(self.port_field.text))

    @ConnectionSuccessSignal.global_listener
    def on_connect(self, target):
        self.visible = False

    @ConnectionErrorSignal.global_listener
    def on_error(self, error, target, signal):
        self.connect_message.text = str(error)

    def update(self, delta_time):
        self.connect_button.frozen = self.port_field.invalid
        self.matchmaker.update()
        #self.sprite_timer.update(delta_time)


class SamanthaPanel(Panel):

    def __init__(self, system):
        super().__init__(system, "Samantha_Overlay")

        aspect = bge.render.getWindowWidth() / bge.render.getWindowHeight()
        scene = system.scene

        camera = scene.objects['Samantha_Camera']

        self.video_source = bge.texture.ImageRender(scene, camera)
        self.video_source.background = 255, 255, 255, 255

        self.video = bgui.ImageRender(parent=self, name="Samantha_Video",
                                    pos=[0, 0], size=[0.2, 0.2],
                                    aspect=aspect, source=self.video_source)


class Notification(bgui.Frame):
    default_size = [1.0, 0.1]

    def __init__(self, parent, message, alive_time=5.0,
                 fade_time=0.25, **kwargs):
        super().__init__(parent=parent,
                         name="notification_{}".format(uuid.uuid4()),
                         size=self.default_size[:],
                         **kwargs)

        self._timers = []

        thin_bar_height = 0.125
        main_bar_width = 0.985

        self.upper_bar = bgui.Frame(parent=self, name="upper_bar",
                                    size=[1.0, thin_bar_height],
                                    options=CENTERX,
                                    pos=[0.0, 1 - thin_bar_height])

        self.lower_bar = bgui.Frame(parent=self, name="lower_bar",
                                    size=[1.0, thin_bar_height],
                                    options=CENTERX,
                                    pos=[0.0, 0])

        self.middle_bar = bgui.Frame(parent=self, name="middle_bar",
                                    size=[main_bar_width, 1 - (2 * thin_bar_height)],
                                    options=CENTERED)

        self.message_text = bgui.Label(parent=self,
                                       name="notification_label",
                                       text=message.upper(),
                                       options=CENTERED,
                                       pos=[0.0, 0.0],
                                       font=bge.logic.expandPath("//themes/agency.ttf"),
                                       pt_size=45, color=[0.4, 0.4, 0.4, 1])

        self.upper_bar.colors = [[0, 0, 0, 1]] * 4
        self.lower_bar.colors = [[0, 0, 0, 1]] * 4
        self.middle_bar.colors = [[0.93, 0.93, 0.93, 0.75]] * 4

        self.initial_position = self._base_pos[:]
        self.initial_height = self._base_size[:]

        self.fade_time = fade_time
        self.alive_time = alive_time

        # Record of components
        components = [self.upper_bar, self.middle_bar,
                           self.lower_bar, self.message_text]
        component_colors = [copy.deepcopy(self._get_color(c))
                                 for c in components]
        self.components = dict(zip(components, component_colors))

        # Add alive timer
        status_timer = ManualTimer(target_value=self.alive_time)
        status_timer.on_target = self.alive_expired
        self.add_timer(status_timer, "status")

        self.on_death = None
        self.is_visible = None

    def _set_color(self, component, color):
        try:
            component.colors[:] = color
        except AttributeError:
            component.color[:] = color[0]

    def _get_color(self, component):
        try:
            return component.colors
        except AttributeError:
            return [component.color]

    def _interpolate(self, target, factor):
        factor = min(max(0.0, factor), 1.0)
        i_x, i_y = self.initial_position

        diff_x = target[0] - i_x
        diff_y = target[1] - i_y

        return [i_x + (diff_x * factor), i_y + (diff_y * factor)]

    def add_timer(self, timer, name=""):
        initial_cb = timer.on_target

        def on_target():
            if callable(initial_cb):
                initial_cb()
            timer.delete()

            self._timers.remove(timer)

        timer.on_target = on_target
        self._timers.append(timer)

    def fade_opacity(self, interval=0.5, out=True):
        fade_timer = ManualTimer(target_value=interval)

        def update_fade():
            alpha = (1 - fade_timer.progress) if out else fade_timer.progress
            for (component, colour) in self.components.items():
                new_colour = [[corner[0], corner[1], corner[2], alpha * corner[3]]
                              for corner in colour]
                self._set_color(component, new_colour)

        fade_timer.on_update = update_fade
        self.add_timer(fade_timer, "fade_{}".format("out" if out else "in"))

    def alive_expired(self):
        # Update position
        target = [self.initial_position[0] + 0.2, self.initial_position[1]]

        self.move_to(target, self.fade_time, note_position=False)
        self.fade_opacity(self.fade_time, out=True)

        death_timer = ManualTimer(target_value=self.fade_time,
                                  on_target=self.on_cleanup)
        self.add_timer(death_timer, "death_timer")

    def move_to(self, target, interval=0.5, note_position=True):
        '''Moves notification to a new position'''
        move_timer = ManualTimer(target_value=interval)

        def update_position():
            factor = move_timer.progress
            self.position = self._interpolate(target, factor)

        target_cb = lambda: setattr(self, "initial_position", self._base_pos[:])

        move_timer.on_update = update_position
        if note_position:
            move_timer.on_target = target_cb

        self.add_timer(move_timer, "mover")

    def on_cleanup(self):
        '''Remove any circular references'''
        _on_death = self.on_death
        del self.on_death
        del self.is_visible
        if callable(_on_death):
            _on_death()

    def update(self, delta_time):
        '''Update all active timers'''
        if callable(self.is_visible):
            _visible = self.visible
            self.visible = self.is_visible()
            if self.visible and not _visible:
                self.fade_opacity(self.fade_time, out=False)

        for timer in self._timers[:]:
            timer.update(delta_time)


class NotificationPanel(Panel):

    def __init__(self, system):
        super().__init__(system, "NotificationPanel")

        self._notifications = []
        self._free_slot = []

        self.start_position = [1 - Notification.default_size[0],
                               1 - Notification.default_size[1]]
        self.entry_padding = 0.03
        self.panel_padding = 0.01

        size = [0.2, 0.5]
        pos = [1 - size[0] - self.panel_padding,
              1 - self.panel_padding - size[1]]

        self.notifications = bgui.Frame(parent=self, name="NotificationsPanel",
                                        size=size, pos=pos)

    @BroadcastMessage.global_listener
    def add_notification(self, message, alive_time=5.0):
        if self._notifications:
            position = self._notifications[-1].initial_position
            position = [position[0], position[1] -
                        self._notifications[-1].initial_height[1]]

        else:
            position = self.start_position[:]

        # Apply padding
        position[1] -= self.entry_padding

        notification = Notification(self.notifications, message, pos=position,
                                    alive_time=alive_time)
        notification.visible = False

        self._notifications.append(notification)
        notification.on_death = lambda: self.delete_notification(notification)
        notification.is_visible = lambda: bool(notification.position[1] >
                                               self.notifications.position[1])
        return notification

    def delete_notification(self, notification):
        self._notifications.remove(notification)
        self.notifications._remove_widget(notification)

        removed_position = notification.initial_position[:]
        if self._free_slot:
            if self._free_slot[1] > removed_position[1]:
                return

        self._free_slot = removed_position

    def update(self, delta_time):
        for notification in self._notifications[:]:
            if notification.name in self.notifications._children:
                notification.update(delta_time)

        # Handle sliding up when deleting notifications
        if self._free_slot:
            target = self._free_slot
            for new_notification in self._notifications:
                if new_notification.initial_position[1] > target[1]:
                    continue
                new_notification.move_to(target)
                target = new_notification.initial_position
            self._free_slot = []


class BGESystem(System):

    def __init__(self):
        super().__init__()

        self.connect_panel = ConnectPanel(self)
        self.notification_panel = NotificationPanel(self)

    @ConnectionSuccessSignal.global_listener
    def invoke(self, *args, **kwargs):
        ConsoleMessage.invoke("Connected to server", alive_time=4)