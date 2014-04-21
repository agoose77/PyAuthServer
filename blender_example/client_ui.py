from network.decorators import ignore_arguments
from network.signals import ConnectionSuccessSignal, ConnectionErrorSignal
from network.world_info import WorldInfo

from bge_network.controllers import PlayerController
from bge_network.signals import ReceiveMessage
from bge_network.timer import Timer, ManualTimer

from .replication_infos import TeamReplicationInfo
from .signals import *
from .matchmaker import Matchmaker
from .ui import *

from bge import logic, render
from bgui import Image, Frame, FrameButton, Label, ListBox, TextInput
from blf import dimensions as font_dimensions
from copy import deepcopy
from functools import partial
from uuid import uuid4 as random_id


def make_gradient(colour, factor, top_down=True):
    by_factor = [v * factor  if i != 3 else v for i, v in enumerate(colour)]
    result = [by_factor, by_factor, colour, colour]
    return result if top_down else list(reversed(result))


def framed_element(parent, id_name, element_type, frame_options, label_options):
    name = "{}_{}".format(id_name, element_type.__name__)
    group = Frame(parent=parent,
                             name="{}_frame".format(name),
                             options=CENTERY,
                             sub_theme="RowGroup",
                             **frame_options)

    label_options.update(dict(parent=group, name="{}".format(name), options=CENTERED))
    try:
        element = element_type(**label_options)
    except ZeroDivisionError:
        element = element_type(size=[1, 1], **label_options)
    return group, element


def make_adjacent(*elements, full_size=None):
    pos = elements[0]._base_pos

    if full_size:
        factor = full_size / sum(x._base_size[0] for x in elements)
    else:
        factor = 1

    for element in elements:
        size = [element._base_size[0] * factor,
                element._base_size[1]]
        element._update_position(size[:], pos[:])
        pos = [pos[0] + size[0], pos[1]]


class ConnectPanel(Panel):

    def __init__(self, system):
        super().__init__(system, "Connect")

        self.aspect = render.getWindowWidth() / render.getWindowHeight()

        self.center_column = Frame(parent=self, name="center",
                                        size=[0.8, 0.8],
                                        options=CENTERED,
                                        sub_theme="ContentBox")

        self.connect_label = Label(parent=self.center_column,
                                        name="label",
                                        pos=[0.0, 0.025],
                                        text="Connection Wizard",
                                        options=CENTERX,
                                        sub_theme="Title")

        self.connection_row = Frame(parent=self.center_column,
                                         name="connection_frame",
                                         size=[0.8, 0.08],
                                         pos=[0.0, 0.85],
                                         sub_theme="ContentRow",
                                         options=CENTERX)

        # Data input
        self.data_row = Frame(parent=self.center_column,
                                   name="data_frame",
                                   size=[0.8, 0.08],
                                   pos=[0.0, 0.77],
                                   sub_theme="ContentRow",
                                   options=CENTERX)

        # IP input
        self.addr_label_frame, _ = framed_element(self.connection_row,
                                               "addr",
                                               Label,
                                               dict(size=[0.3, 1.0],
                                                    pos=[0.0, 0.5]),
                                               dict(text="IP Address"))

        self.addr_input_frame, self.addr_field = framed_element(self.connection_row,
                                               "addr",
                                               TextInput,
                                               dict(size=[0.4, 1.0],
                                                    pos=[0.0, 0.5]),
                                               dict(allow_empty=False,
                                                    text="localhost"))

        self.port_label_frame, _ = framed_element(self.connection_row,
                                              "port",
                                              Label,
                                              dict(size=[0.2, 1.0],
                                                   pos=[0.0, 0.5]),
                                              dict(text="Port"))

        self.port_input_frame, self.port_field = framed_element(self.connection_row,
                                               "port",
                                               TextInput,
                                               dict(size=[0.1, 1.0],
                                                    pos=[0.0, 0.5]),
                                               dict(allow_empty=False,
                                                    text="1200"))
        make_adjacent(self.addr_label_frame, self.addr_input_frame,
                      self.port_label_frame, self.port_input_frame)

        self.error_label_frame, _ = framed_element(self.data_row,
                                                "error",
                                                Label,
                                                dict(size=[0.3, 1.0],
                                                     pos=[0.0, 0.5]),
                                                dict(text="Information")
                                                )

        self.error_message_frame, self.error_body_field = framed_element(self.data_row,
                                                  "error_msg",
                                                  Label,
                                                  dict(size=[0.7, 1.0],
                                                       pos=[0.0, 0.5]),
                                                  dict(text="")
                                                  )

        make_adjacent(self.error_label_frame, self.error_message_frame)

        self.controls_row = Frame(parent=self.center_column,
                                   name="server_controls", size=[0.8, 0.08],
                                   pos=[0.0, 0.69], sub_theme="ContentRow",
                                   options=CENTERX)
 
        self.refresh_button = FrameButton(self.controls_row, "refresh_button",
                                               size=[0.2, 1.0], pos=[0.0, 0.0],
                                               text="Refresh")
        self.connect_button = FrameButton(self.controls_row, "connect_button",
                                               size=[0.2, 1.0], pos=[0.0, 0.0],
                                               text="Connect")

        self.match_label_frame, _ = framed_element(self.controls_row,
                                              "matchmaker",
                                              Label,
                                              dict(size=[0.2, 1.0],
                                                   pos=[0.0, 0.5]),
                                              dict(text="Matchmaker"))

        self.match_input_frame, self.match_field = framed_element(self.controls_row,
                                               "matchmaker",
                                               TextInput,
                                               dict(size=[0.5, 1.0],
                                                    pos=[0.0, 0.5]),
                                               dict(allow_empty=False,
                        text="http://coldcinder.co.uk/networking/matchmaker"))

        make_adjacent(self.refresh_button, self.connect_button,
                      full_size=0.3)
        make_adjacent(self.refresh_button, self.connect_button,
                      self.match_label_frame, self.match_input_frame)

        self.servers_list = Frame(parent=self.center_column,
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

        self.servers_box = ListBox(parent=self.servers_list,
                                        name="servers",
                                        items=self.servers, padding=0.0,
                                        size=[1.0, 1.0],
                                        pos=[0.0, 0.0])
        self.servers_box.renderer = TableRenderer(self.servers_box,
                                              labels=self.server_headers)

        self.sprite = SpriteSequence(self.error_message_frame, "sprite",
                                     logic.expandPath("//themes/ui/loading_sprite.tga"),
                                     length=20, loop=True,  size=[0.1, 0.6],
                                     aspect=1, relative_path=False,
                                     options=CENTERY)
        self.sprite_timer = Timer(end=1 / 20, repeat=True)
        self.sprite_timer.on_target=self.sprite.next_frame

        # Allows input fields to accept input when not hovered
        self.connection_row.is_listener = True

        self.connect_button.on_click = self.do_connect
        self.refresh_button.on_click = self.do_refresh
        self.servers_box.on_select = self.do_select

        self.uses_mouse = True
        self.sprite.visible = False

    def display_error(self, text):
        self.error_body_field.text = text

    def do_select(self, list_box, entry):
        data = dict(entry)

        self.addr_field.text = data['address']
        self.port_field.text = data['port']

    def do_connect(self, button):
        ConnectToSignal.invoke(self.addr_field.text, int(self.port_field.text))
        self.sprite.visible = True

    def do_refresh(self, button):
        self.matchmaker.url = self.match_field.text
        self.matchmaker.perform_query(self.evaluate_servers,
                                      self.matchmaker.server_query())
        self.sprite.visible = True

    def evaluate_servers(self, response):
        self.servers[:] = [tuple(entry.items()) for entry in response]
        self.display_error("Refreshed Server List" if self.servers
                                    else "No Servers Found")
        self.sprite.visible = False

    @ConnectionSuccessSignal.global_listener
    def on_connected(self, target):
        self.visible = False

    @ConnectionErrorSignal.global_listener
    def on_error_occurred(self, error, target, signal):
        self.display_error(str(error))
        self.sprite.visible = False

    def update(self, delta_time):
#         self.connect_button.frozen = self.port_field.invalid
        self.matchmaker.update()


class TeamPanel(Panel):

    def __init__(self, system):
        super().__init__(system, "Team")

        self.aspect = render.getWindowWidth() / render.getWindowHeight()

        self.center_column = Frame(parent=self, name="center",
                                        size=[0.8, 0.8],
                                        options=CENTERED,
                                        sub_theme="ContentBox")

        self.team_label = Label(parent=self.center_column,
                                        name="label",
                                        pos=[0.0, 0.025],
                                        text="Choose Team",
                                        options=CENTERX,
                                        sub_theme="Title")

        self.selection_row = Frame(parent=self.center_column,
                                         name="connection_frame",
                                         size=[0.8, 0.08],
                                         pos=[0.0, 0.85],
                                         sub_theme="ContentRow",
                                         options=CENTERX)

        self.left_button = FrameButton(self.selection_row, "left_button",
                                               size=[0.5, 1.0], pos=[0.0, 0.0],
                                               text="")

        self.right_button = FrameButton(self.selection_row, "right_button",
                                               size=[0.5, 1.0], pos=[0.5, 0.0],
                                               text="")

        self.uses_mouse = True
        self.visible = False

    def display_error(self, text):
        self.error_body_field.text = text

    def do_select(self, list_box, entry):
        data = dict(entry)

        self.addr_field.text = data['address']
        self.port_field.text = data['port']

    def do_connect(self, button):
        ConnectToSignal.invoke(self.addr_field.text, int(self.port_field.text))
        self.sprite.visible = True

    def do_refresh(self, button):
        self.matchmaker.url = self.match_field.text
        self.matchmaker.perform_query(self.evaluate_servers,
                                      self.matchmaker.server_query())
        self.sprite.visible = True

    def evaluate_servers(self, response):
        self.servers[:] = [tuple(entry.items()) for entry in response]
        self.display_error("Refreshed Server List" if self.servers
                                    else "No Servers Found")
        self.sprite.visible = False

    @ConnectionSuccessSignal.global_listener
    def on_connected(self, target):
        self.visible = True

    @TeamSelectionUpdatedSignal.global_listener
    def on_team_selected(self, target):
        self.visible = False

    def update(self, delta_time):
        if self.left_button.on_click:
            return

        team_replicables = WorldInfo.subclass_of(TeamReplicationInfo)
        try:
            left, right = team_replicables[:2]
        except ValueError:
            return

        player_controller = PlayerController.get_local_controller()

        if not player_controller:
            return

        # Save callbacks for buttons
        self.left_button.text = left.name
        self.right_button.text = right.name

        self.left_button.on_click = ignore_arguments(partial(player_controller.set_team, left))
        self.right_button.on_click = ignore_arguments(partial(player_controller.set_team, right))


class TimerMixins:

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._timers = []

    def add_timer(self, timer, name=""):
        '''Registers a timer for monitoring'''
        def on_stop():
            timer.delete()
            self._timers.remove(timer)

        timer.on_stop = on_stop
        self._timers.append(timer)

    def update(self, delta_time):
        '''Update all active timers'''
        for timer in self._timers[:]:
            timer.update(delta_time)


class Notification(TimerMixins, Frame):
    default_size = [1.0, 0.06]

    def __init__(self, parent, message,
                 alive_time=5.0,
                 fade_time=0.25,
                 font_size=35, **kwargs):
        super().__init__(parent=parent,
                         name="notification_{}".format(random_id()),
                         size=self.default_size[:],
                         **kwargs)

        self.fade_time = fade_time
        self.alive_time = alive_time
        self.message = message

        self.middle_bar = Frame(parent=self, name="middle_bar",
                                    size=[1, 1],
                                    options=CENTERED)

        self.message_text = Label(parent=self,
                                       name="notification_label",
                                       text=message.upper(),
                                       options=CENTERED,
                                       pos=[0.0, 0.0],
                                       pt_size=font_size, color=[0.1, 0.1, 0.1, 1])

        # Determine if overflowing
        width_running = 0
        notification_width = self.size[0]
        message_widths = self.get_message_widths(self.message_text)

        for index, width in enumerate(message_widths):
            width_running += width
            if width_running >= notification_width:
                break
        else:
            index = None

        self.message_index_end = index

        if index:
            self.message_text.text = message[:index]
            status_timer = ManualTimer(end=self.alive_time * 0.9)
            status_timer.on_update = partial(self.scroll_message, status_timer)
            self.add_timer(status_timer, "scroll")

        self.middle_bar.colors = [[1, 1, 1, 0.6]] * 4

        self.initial_position = self._base_pos[:]
        self.initial_height = self._base_size[:]

        # Record of components
        components = [self.middle_bar, self.message_text]
        component_colors = [deepcopy(self._get_color(c)) for c in components]
        self.components = dict(zip(components, component_colors))

        # Add alive timer
        status_timer = ManualTimer(end=self.alive_time)
        status_timer.on_target = self.alive_expired
        self.add_timer(status_timer, "status")

        self.on_death = None
        self.is_visible = None

    def get_message_widths(self, label):
        return [(font_dimensions(label.fontid, char * 20)[0] / 20)
                for char in label.text]

    def scroll_message(self, timer):
        message = self.message
        message_limit = self.message_index_end
        max_shift = len(message) - message_limit
        shift_index = round(timer.progress * max_shift)
        self.message_text.text = message[shift_index:
                                         shift_index + message_limit]

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

    def fade_opacity(self, interval=0.5, out=True):
        fade_timer = ManualTimer(end=interval)

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

        death_timer = ManualTimer(end=self.fade_time)
        death_timer.on_target = self.on_cleanup

        self.add_timer(death_timer, "death_timer")

    def move_to(self, target, interval=0.5, note_position=True):
        '''Moves notification to a new position'''
        move_timer = ManualTimer(end=interval)

        def update_position():
            factor = move_timer.progress
            self.position = self._interpolate(target, factor)

        target_cb = lambda: setattr(self, "initial_position", self._base_pos[:])

        move_timer.on_update = update_position
        if note_position:
            #move_timer.on_target = target_cb
            target_cb()

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

        super().update(delta_time)


class UIPanel(TimerMixins, Panel):

    def __init__(self, system):
        super().__init__(system, "UIPanel")

        self._notifications = []
        self._free_slot = []

        self.start_position = [1 - Notification.default_size[0],
                               1 - Notification.default_size[1]]
        self.entry_padding = 0.02
        self.panel_padding = 0.01

        # Main UI
        self.dark_grey = [0.1, 0.1, 0.1, 1]
        self.light_grey = [0.3, 0.3, 0.3, 1]
        self.faded_grey = [0.3, 0.3, 0.3, 0.3]
        self.faded_white = [1, 1, 1, 0.6]
        self.error_red = [1, 0.05, 0.05, 1]
        self.font_size = 32

        main_size = [0.2, 0.8]
        main_pos = [1 - main_size[0] - self.panel_padding,
              1 - self.panel_padding - main_size[1]]

        self.notifications = Frame(parent=self, name="NotificationsPanel",
                                        size=main_size[:], pos=main_pos[:])
        self.notifications.colors = [self.faded_grey] * 4

        self.weapons_box = Frame(self, "weapons", size=[main_size[0], 0.25],
                                      pos=[main_pos[0], 0.025])

        self.icon_box = Frame(self.weapons_box, "icons", size=[1.0, 0.5],
                                   pos=[0.0, 0.5])
        self.stats_box = Frame(self.weapons_box, "stats", size=[1.0, 0.5],
                                    pos=[0.0, 0.0])

        self.weapon_icon = Image(self.icon_box, "icon", "",
                                      size=[0.1, 1.0], aspect=314 / 143,
                                      pos=[0.0, 0.0], options=CENTERED)

        bar_size = [1.0, 0.35]
        bar_margin = 0.025
        bar_pos = [max(1 - bar_size[0] - bar_margin, 0),  0.25]

        self.icon_bar = Frame(self.icon_box, "icon_bar", size=bar_size[:],
                                   pos=bar_pos[:])

        self.icon_shadow = Image(self.icon_bar, "icon_shadow",
                                      "ui/checkers_border.tga",
                                    size=[1.6, 1.6], aspect=1.0,
                                    pos=[0.8, 0], options=CENTERY)

        self.icon_back = Frame(self.icon_shadow, "icon_back",
                                    size=[0.8, 0.8], aspect=1.0, options=CENTERED)

        self.icon_middle = Frame(self.icon_back, "icon_middle",
                                    size=[0.9, 0.9], aspect=1.0,
                                    pos=[0.0, 0], options=CENTERED)
        self.icon_theme = Frame(self.icon_middle, "icon_theme",
                                    size=[1.0, 1.0], aspect=1.0,
                                    pos=[0.0, 0], options=CENTERED)
        self.icon_checkers = Image(self.icon_middle, "icon_checkers",
                                        "ui/checkers_overlay.tga",
                                        size=[1.0, 1.0], aspect=1.0,
                                        pos=[0.0, 0.0], options=CENTERED)

        self.weapon_name = Label(self.icon_bar,
                                      name="weapon_name",
                                      text="The Spitter",
                                      pt_size=self.font_size,
                                      shadow=True,
                                      shadow_color=self.light_grey,
                                      options=CENTERY,
                                      pos=[0.05, 0.0],
                                      color=self.dark_grey)

        self.rounds_info = Frame(self.stats_box, "clips_info",
                                      pos=[0.0, 0.7], size=[0.6, 0.35])
        self.clips_info = Frame(self.stats_box, "rounds_info",
                                     pos=[0.0, 0.2], size=[0.6, 0.35])
        self.grenades_info = Frame(self.stats_box, "grenades_info",
                                        pos=[0.6, 0.2], size=[0.35, 0.85])

        self.frag_img = Image(self.grenades_info,
                                   "frag_img",
                                   "ui/frag.tga",
                                   pos=[0.0, 0.0],
                                   size=[1, 0.9],
                                   aspect=41 / 92,
                                     options=CENTERY)
        self.flashbang_img = Image(self.grenades_info,
                                        "flashbang_img",
                                        "ui/flashbang.tga",
                                        pos=[0.5, 0.0],
                                        size=[1, 0.9],
                                        aspect=41 / 92,
                                        options=CENTERY)

        self.frag_info = Frame(self.frag_img, "frag_info", size=[0.6, 0.35],
                                   aspect=1, pos=[0.0, 0.0], options=CENTERED)
        self.frag_box = Frame(self.frag_info, "frag_box", size=[1, 1],
                                   pos=[0.0, 0.0], options=CENTERED)

        self.frag_label = Label(self.frag_box,
                                     "frag_label",
                                     "4",
                                      pt_size=self.font_size,
                                      options=CENTERED,
                                      pos=[0.05, 0.0],
                                      color=self.dark_grey)

        self.flashbang_info = Frame(self.flashbang_img,
                                         "flashbang_info",
                                        size=[0.6, 0.35],
                                        aspect=1,
                                        options=CENTERED)

        self.flashbang_box = Frame(self.flashbang_info, "flashbang_box",
                                        size=[1, 1],
                                        pos=[0.0, 0.0],
                                        options=CENTERED)

        self.flashbang_label = Label(self.flashbang_box,
                                          "flashbang_label", "4",
                                          pt_size=self.font_size,
                                          options=CENTERED, pos=[0.05, 0.0],
                                          color=self.dark_grey)

        self.rounds_img = Image(self.rounds_info, "rounds_img",
                                     "ui/info_box.tga", pos=[0.0, 0.0],
                                     size=[1, 1], aspect=1.0, options=CENTERY)
        self.clips_img = Image(self.clips_info, "clips_img",
                                    "ui/info_box.tga", pos=[0.0, 0.0],
                                     size=[1, 1], aspect=1.0, options=CENTERY)

        self.rounds_box = Frame(self.rounds_info, "rounds_box",
                                     size=[0.6, 1.0], pos=[0.3, 0.0],
                                     options=CENTERY)
        self.clips_box = Frame(self.clips_info, "clips_box",
                                    size=[0.6, 1.0], pos=[0.3, 0.0],
                                    options=CENTERY)

        self.rounds_label = Label(self.rounds_box,
                                       name="rounds_label",
                                       text="ROUNDS",
                                       pt_size=self.font_size,
                                       options=CENTERY,
                                       pos=[0.05, 0.0],
                                       color=self.dark_grey)

        self.clips_label = Label(self.clips_box,
                                      name="clips_label",
                                      text="CLIPS",
                                      pt_size=self.font_size,
                                      options=CENTERY,
                                      pos=[0.05, 0.0],
                                      color=self.dark_grey)

        self.rounds_value = Label(self.rounds_img,
                                       name="rounds_value",
                                       text="100",
                                       pt_size=self.font_size,
                                       options=CENTERED,
                                       pos=[0.05, 0.0],
                                       color=self.dark_grey)

        self.clips_value = Label(self.clips_img,
                                      name="clips_value",
                                      text="4",
                                      pt_size=self.font_size,
                                      options=CENTERED,
                                      pos=[0.05, 0.0],
                                      color=self.dark_grey)

        self.icon_back.colors = [self.dark_grey] * 4
        self.icon_middle.colors = [self.light_grey] * 4
        self.rounds_box.colors = [self.faded_white] * 4
        self.clips_box.colors = [self.faded_white] * 4
        self.flashbang_info.colors = [self.faded_white] * 4
        self.frag_info.colors = [self.faded_white] * 4
        self.frag_box.colors = [self.faded_white] * 4
        self.flashbang_box.colors = [self.faded_white] * 4
        self.icon_bar.colors = [self.faded_white] * 4

        self.visible = False

        self.entries = {"ammo": (self.rounds_info, self.rounds_value),
                         "clips": (self.clips_info, self.clips_value),
                         "frags": (self.frag_box, self.frag_label),
                         "flashbangs": (self.flashbang_box, self.flashbang_label)}
        self.handled_concerns = {}

        self.health_indicator = Image(self, "health",
                                        "ui/health_overlay.tga",
                                        size=[1.0, 1.0],
                                        pos=[0.0, 0.0], options=CENTERED)
        self.health_indicator.color[-1] = 0.0

    @UIWeaponDataChangedSignal.global_listener
    def update_entry(self, name, value):
        value_field = self.entries[name][1]
        value_field.text = str(value)

    def create_glow_animation(self, entry):
        glow = ManualTimer(1, repeat=True)
        glow.on_update = partial(self.fading_animation, entry, glow)
        self.add_timer(glow, "glow")
        return glow

    @property
    def theme_colour(self):
        return self.icon_theme.colors[0]

    @theme_colour.setter
    def theme_colour(self, value):
        self.icon_theme.colors = make_gradient(value, 1 / 3)

    @TeamSelectionUpdatedSignal.global_listener
    def on_team_selected(self, target):
        self.visible = True

    @UIHealthChangedSignal.global_listener
    def health_changed(self, health):
        self.health_indicator.color[-1] = 1 - (health/100)

    @UIWeaponChangedSignal.global_listener
    def weapon_changed(self, weapon):
        self.weapon_name.text = weapon.__class__.__name__
        self.weapon_icon.update_image(weapon.icon_path)
        self.theme_colour = weapon.theme_colour

    def fading_animation(self, entry, timer):
        err = (self.error_red[0], self.error_red[1],
               self.error_red[2], 1 - timer.progress)
        entry.colors = [err] * 4

    def update(self, delta_time):
        for notification in self._notifications[:]:
            if notification.name in self.notifications._children:
                notification.update(delta_time)

        # Handle sliding up when deleting notifications
        y_shift = Notification.default_size[1] + self.entry_padding
        for index, notification in enumerate(self._notifications):
            intended_y = self.start_position[1] - (index * y_shift)
            position_y = notification.initial_position[1]

            if (position_y == intended_y):
                continue

            notification.move_to([self.start_position[0], intended_y])

        # Create any alert timers
        for name, (field, label) in self.entries.items():
            if label.text == "0":
                if not name in self.handled_concerns:
                    ReceiveMessage.invoke("Ran out of {}!".format(name), alive_time=10)
                    self.handled_concerns[name] = self.create_glow_animation(
                                                                         field)

        # Check for handled timers
        handled = []
        for name, timer in self.handled_concerns.items():
            field, label = self.entries[name]

            if label.text != "0":
                timer.stop()
                handled.append(name)

        # Remove handled UI timers
        for handled_name in handled:
            self.handled_concerns.pop(handled_name)

        super().update(delta_time)

    @ReceiveMessage.global_listener
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
                                    alive_time=alive_time, font_size=self.font_size)
        notification.visible = False

        self._notifications.append(notification)
        notification.on_death = lambda: self.delete_notification(notification)
        notification.is_visible = lambda: bool(notification.position[1] >
                                               self.notifications.position[1])
        return notification

    def delete_notification(self, notification):
        self._notifications.remove(notification)
        self.notifications._remove_widget(notification)


class BGESystem(System):

    def __init__(self):
        super().__init__()

        self.connect_panel = ConnectPanel(self)
        self.ui_panel = UIPanel(self)
        self.choose_team = TeamPanel(self)

    @ConnectionSuccessSignal.global_listener
    def invoke(self, *args, **kwargs):
        ReceiveMessage.invoke("Connected to server", alive_time=4)
