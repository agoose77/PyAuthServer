from network.decorators import ignore_arguments
from network.signals import ConnectionSuccessSignal, ConnectionErrorSignal
from network.world_info import WorldInfo

from bge_network.controllers import PlayerController
from bge_network.signals import ReceiveMessage
from bge_network.timer import Timer
from bge_network.resources import ResourceManager
from bge_network.utilities import lerp

from .replication_infos import TeamReplicationInfo
from .signals import *
from .matchmaker import Matchmaker
from .ui import *

from bge import logic, render
from bgui import Image, Frame, FrameButton, Label, ListBox, TextInput, BGUI_INPUT_INTEGER
from blf import dimensions as font_dimensions
from copy import deepcopy
from functools import partial
from time import monotonic
from socket import inet_aton
from uuid import uuid4 as random_id


def create_gradient(colour, factor, top_down=True):
    shifted_colour = [v * factor if i != 3 else v for i, v in enumerate(colour)]
    gradient_corners = [shifted_colour, shifted_colour, colour, colour]

    if not top_down:
        gradient_corners.reverse()

    return gradient_corners


def create_framed_element(parent, id_name, element_type, frame_options, label_options):
    element_name = "{}_{}".format(id_name, element_type.__name__)
    group = Frame(parent=parent, name="{}_frame".format(element_name), options=CENTERY, sub_theme="RowGroup",
                  **frame_options)

    label_options.update(dict(parent=group, name="{}".format(element_name), options=CENTERED))

    try:
        element = element_type(**label_options)

    except ZeroDivisionError:
        element = element_type(size=[1, 1], **label_options)

    return group, element


def create_adjacent(*elements, full_size=None):
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


def set_colour(widget, colour):
    """Set the colours of a widget

    :param widget: BGUI widget
    :param colour: list of new colours"""
    try:
        widget.colors[:] = colour

    except AttributeError:
        widget.color[:] = colour[0]


def get_colour(widget):
    """Get the colours of a widget

    :param widget: BGUI widget
    :returns: widget colours list"""
    try:
        return widget.colors

    except AttributeError:
        return [widget.color]


class DeltaTimeDecorator:

    def __init__(self, func):
        self.func = func
        self.last_time = monotonic()

    def __call__(self, *args, **kwargs):
        now = monotonic()
        delta_time = now - self.last_time
        self.last_time = now
        self.func(delta_time, *args, **kwargs)


class FrameRateDecorator:

    def __init__(self, func):
        self.func = func

    def __call__(self, *args, **kwargs):
        average_fps = logic.getAverageFrameRate()
        self.func(average_fps, *args, **kwargs)


class ConnectPanel(Panel):

    def __init__(self, system):
        super().__init__(system, "Connect")

        self.aspect = render.getWindowWidth() / render.getWindowHeight()

        self.center_column = Frame(parent=self, name="center", size=[0.8, 0.8],  options=CENTERED,
                                   sub_theme="ContentBox")

        self.connect_label = Label(parent=self.center_column, name="label", pos=[0.0, 0.025], text="Connection Wizard",
                                   options=CENTERX, sub_theme="Title")

        self.connection_row = Frame(parent=self.center_column, name="connection_frame", size=[0.8, 0.08],
                                    pos=[0.0, 0.85], sub_theme="ContentRow", options=CENTERX)

        # Data input
        self.data_row = Frame(parent=self.center_column, name="data_frame", size=[0.8, 0.08], pos=[0.0, 0.77],
                              sub_theme="ContentRow", options=CENTERX)

        # IP input
        self.address_label_frame, _ = create_framed_element(self.connection_row, "addr",  Label, dict(size=[0.3, 1.0],
                                                                                                   pos=[0.0, 0.5]),
                                                         dict(text="IP Address"))

        self.address_input_frame, self.address_field = create_framed_element(self.connection_row, "addr", TextInput,
                                                                       dict(size=[0.4, 1.0], pos=[0.0, 0.5]),
                                                                       dict(allow_empty=False, text="localhost"))

        self.address_field.on_validate = self.validate_ip

        self.port_label_frame, _ = create_framed_element(self.connection_row, "port", Label, dict(size=[0.2, 1.0],
                                                                                                  pos=[0.0, 0.5]),
                                                         dict(text="Port"))

        self.port_input_frame, self.port_field = create_framed_element(self.connection_row, "port", TextInput,
                                                                       dict(size=[0.1, 1.0], pos=[0.0, 0.5]),
                                                                       dict(allow_empty=False, text="1200",
                                                                            type=BGUI_INPUT_INTEGER))
        create_adjacent(self.address_label_frame, self.address_input_frame, self.port_label_frame, self.port_input_frame)

        self.error_label_frame, _ = create_framed_element(self.data_row, "error", Label, dict(size=[0.3, 1.0],
                                                                                              pos=[0.0, 0.5]),
                                                          dict(text="Information"))

        self.error_message_frame, self.error_body_field = create_framed_element(self.data_row, "error_msg", Label,
                                                                                dict(size=[0.7, 1.0], pos=[0.0, 0.5]),
                                                                                dict(text=""))

        create_adjacent(self.error_label_frame, self.error_message_frame)

        self.controls_row = Frame(parent=self.center_column, name="server_controls", size=[0.8, 0.08], pos=[0.0, 0.69],
                                  sub_theme="ContentRow", options=CENTERX)

        self.refresh_button = FrameButton(self.controls_row, "refresh_button", size=[0.2, 1.0], pos=[0.0, 0.0],
                                          text="Refresh")
        self.connect_button = FrameButton(self.controls_row, "connect_button", size=[0.2, 1.0], pos=[0.0, 0.0],
                                          text="Connect")

        self.match_label_frame, _ = create_framed_element(self.controls_row, "matchmaker", Label, dict(size=[0.2, 1.0],
                                                                                                       pos=[0.0, 0.5]),
                                                          dict(text="Matchmaker"))

        self.match_input_frame, self.match_field = create_framed_element(self.controls_row, "matchmaker", TextInput,
                                                                         dict(size=[0.5, 1.0], pos=[0.0, 0.5]),
                                                                         dict(allow_empty=False,
                                                                              text="http://coldcinder.co.uk/networking/"
                                                                                   "matchmaker"))

        create_adjacent(self.refresh_button, self.connect_button, full_size=0.3)
        create_adjacent(self.refresh_button, self.connect_button, self.match_label_frame, self.match_input_frame)

        self.servers_list = Frame(parent=self.center_column, name="server_list", size=[0.8, 0.6], pos=[0.0, 0.09],
                                  sub_theme="ContentRow", options=CENTERX)
        self.servers = []
        self.server_headers = ["name", "map", "players", "max_players"]

        self.matchmaker = Matchmaker("")

        self.servers_box = ListBox(parent=self.servers_list, name="servers", items=self.servers, padding=0.0,
                                   size=[1.0, 1.0], pos=[0.0, 0.0])
        self.servers_box.renderer = TableRenderer(self.servers_box, labels=self.server_headers)

        # Load sprite resource
        relative_sprite_path = ResourceManager["UI"]['sprites']['loading_sprite.tga']
        absolute_sprite_path = ResourceManager.from_relative_path(relative_sprite_path)

        # Create sprite
        self.sprite = SpriteSequence(self.error_message_frame, "sprite", absolute_sprite_path, length=20, loop=True,
                                     size=[0.1, 0.6], aspect=1, relative_path=False, options=CENTERY)

        # Update sprite
        self.sprite_timer = Timer(end=0.05, repeat=True)
        self.sprite_timer.on_target = self.sprite.next_frame

        # Allows input fields to accept input when not hovered
        self.connection_row.is_listener = True

        # Create event handlers
        self.connect_button.on_click = self.do_connect
        self.refresh_button.on_click = self.do_refresh
        self.servers_box.on_select = self.do_select_server

        # Set configuration for systems
        self.uses_mouse = True
        self.sprite.visible = False

    @property
    def address(self):
        if self.address_field.invalid:
            return None
        return self.address_field.text

    @address.setter
    def address(self, address):
        self.address_field.text = address

    @property
    def port(self):
        if self.port_field.invalid:
            return None
        return int(self.port_field.text)

    @port.setter
    def port(self, port):
        self.port_field.text = str(port)

    @property
    def matchmaker_address(self):
        if self.match_field.invalid:
            return None
        return self.match_field.text

    @ConnectionSuccessSignal.global_listener
    def disable(self):
        """Callback for connection success"""
        self.visible = False

    def do_connect(self, button):
        """Callback for connection button, invokes a connection signal

        :param button: button that was pressed
        """

        errors = []
        if self.address is None:
            errors.append("address")

        if self.port is None:
            errors.append("port")

        if errors:
            tail, *head = errors

            if not head:
                error_string = tail

            else:
                error_string = "{} and {}".format(tail, head[0])

            self.show_message("Invalid {}".format(error_string))
            return

        ConnectToSignal.invoke(self.address, self.port)
        self.sprite.visible = True

    def do_refresh(self, button):
        """Callback for refresh button, perform a matchmaker refresh query

        :param button: button that was pressed
        """
        if self.matchmaker_address is None:
            self.show_message("Invalid matchmaker address")
            return

        self.matchmaker.url = self.matchmaker_address
        self.matchmaker.perform_query(self.on_matchmaker_response, self.matchmaker.server_query())
        self.sprite.visible = True

    def do_select_server(self, list_box, entry):
        """Callback for server selection, update address and port fields with selection

        :param list_box: list box containing entry
        :param entry: server entry that was selected
        """
        selection_data = dict(entry)

        self.address = selection_data['address']
        self.port = selection_data['port']

    @ConnectionErrorSignal.global_listener
    def on_connection_failure(self, error):
        """Callback for connection failure

        :param error: error that occurred
        """
        self.show_message(str(error))
        self.sprite.visible = False

    def on_matchmaker_response(self, response):
        """Callback for matchmaker response, update internal server list and writes status to display

        :param response: matchmaker response dictionary
        """
        self.servers[:] = [tuple(entry.items()) for entry in response]
        self.show_message("Refreshed Server List" if self.servers else "No Servers Found")

        self.sprite.visible = False

    def show_message(self, text):
        """Write message text to display panel

        :param text: text to display
        """
        self.error_body_field.text = text

    def update(self, delta_time):
        """Update matchmaker queue

        :param delta_time: time since last update
        """
        self.matchmaker.update()

    @staticmethod
    def validate_ip(str_):
        """Determine if a string is a valid IP address

        :param str_: IP address string
        :rtype: bool
        """
        if str_ == "localhost":
            return True

        try:
            inet_aton(str_)

        except (OSError, AssertionError):
            return False

        return True


class TeamPanel(Panel):

    def __init__(self, system):
        super().__init__(system, "Team")

        self.aspect = render.getWindowWidth() / render.getWindowHeight()

        self.center_column = Frame(parent=self, name="center", size=[0.8, 0.8], options=CENTERED,
                                   sub_theme="ContentBox")

        self.team_label = Label(parent=self.center_column, name="label", pos=[0.0, 0.025], text="Choose Team",
                                options=CENTERX, sub_theme="Title")

        self.selection_row = Frame(parent=self.center_column, name="connection_frame", size=[0.8, 0.08],
                                   pos=[0.0, 0.85], sub_theme="ContentRow", options=CENTERX)

        self.left_button = FrameButton(self.selection_row, "left_button", size=[0.5, 1.0], pos=[0.0, 0.0], text="")

        self.right_button = FrameButton(self.selection_row, "right_button", size=[0.5, 1.0], pos=[0.5, 0.0], text="")

        self.uses_mouse = True
        self.visible = False

    @ConnectionSuccessSignal.global_listener
    def enable(self):
        """Callback for connection success

        Sets panel visible"""
        self.visible = True

    @TeamSelectionUpdatedSignal.global_listener
    def disable(self):
        """Callback for team selection

        Sets panel invisible"""
        self.visible = False

    def update(self, delta_time):
        if self.left_button.on_click:
            return

        team_info_list = WorldInfo.subclass_of(TeamReplicationInfo)

        try:
            left, right = team_info_list[:2]
        except ValueError:
            return

        player_controller = PlayerController.get_local_controller()

        if not player_controller:
            return

        # Save call-backs for buttons
        self.left_button.text = left.name
        self.right_button.text = right.name

        self.left_button.on_click = ignore_arguments(partial(player_controller.set_team, left))
        self.right_button.on_click = ignore_arguments(partial(player_controller.set_team, right))


class Notification(Frame):

    def __init__(self, parent, message, alive_time=5.0, scroll_time=None, fade_time=0.25, font_size=35, **kwargs):
        super().__init__(parent=parent, name="notification_{}".format(random_id()), **kwargs)

        if scroll_time is None:
            scroll_time = alive_time * 0.9

        self.fade_time = fade_time
        self.alive_time = alive_time
        self.scroll_time = scroll_time
        self.message = message

        has_lifespan = self.alive_time > 0.0

        self.middle_bar = Frame(parent=self, name="middle_bar", size=[1, 1], options=CENTERED)

        self.message_text = Label(parent=self, name="notification_label", text=message.upper(), options=CENTERED,
                                  pos=[0.0, 0.0], pt_size=font_size, color=[0.1, 0.1, 0.1, 1])

        # Determine if overflowing
        self.message_index_end = self.message_overflow_index

        # If we do overflow
        if self.message_index_end:
            self.message_text.text = message[:self.message_index_end]
            status_timer = Timer(end=self.scroll_time, repeat=not has_lifespan, disposable=True)
            status_timer.on_update = partial(self._shift_message, status_timer)

        self.middle_bar.colors = [[1, 1, 1, 0.6]] * 4

        self.initial_position = self._base_pos[:]
        self.initial_height = self._base_size[:]

        # Record of components
        components = [self.middle_bar, self.message_text]
        component_colors = [deepcopy(get_colour(c)) for c in components]
        self.components = dict(zip(components, component_colors))

        # Add alive timer
        if has_lifespan:
            status_timer = Timer(end=self.alive_time, disposable=True)
            status_timer.on_target = self.on_expired

        self.on_death = None
        self.is_visible = None

    def _shift_message(self, timer):
        """Scrolls message text according to timer

        :param timer: Timer instance
        """
        message = self.message
        character_limit = self.message_index_end

        maximum_offset = len(message) - character_limit
        message_offset = round(timer.progress * maximum_offset)

        self.message_text.text = message[message_offset: message_offset + character_limit]

    @property
    def message_overflow_index(self):
        width_running = 0
        notification_width = self.size[0]
        message_widths = self.get_blf_message_widths(self.message_text)

        for index, width in enumerate(message_widths):
            width_running += width
            if width_running >= notification_width:
                return index

    def fade(self, interval=0.5, out=True):
        """Fades notification in/out

        :param interval: time interval
        :param out: fade out[|fade in]
        """

        def _update_fade():
            """Interpolate between initial alpha and target alpha"""
            alpha = (1 - fade_timer.progress) if out else fade_timer.progress
            for (component, colours) in self.components.items():

                colour = []
                for corner in colours:
                    new_corner = corner.copy()
                    new_corner[-1] *= alpha

                    colour.append(new_corner)

                set_colour(component, colour)

        fade_timer = Timer(end=interval, disposable=True)
        fade_timer.on_update = _update_fade

    @staticmethod
    def get_blf_message_widths(label):
        """Determines the width of a label in pixels

        :param label: BGUI label instance
        """
        return [(font_dimensions(label.fontid, char * 20)[0] / 20) for char in label.text]

    def move_to(self, position, interval=0.5, note_position=True):
        """Moves notification to a new position

        :param position: position to move towards
        :param interval: duration of movement
        :param note_position: start from current position(optional)
        """

        def _interpolate_position():
            """Interpolate between initial position and target position"""
            initial = self.initial_position
            factor = move_timer.progress

            x_initial, y_initial = initial
            x_final, y_final = position

            self.position = [lerp(x_initial, x_final, factor),
                        lerp(y_initial, y_final, factor)]

        move_timer = Timer(end=interval, disposable=True)
        move_timer.on_update = _interpolate_position

        if note_position:
            self.initial_position = self._base_pos[:]

    def on_cleanup(self):
        """Remove any circular references"""
        _on_death = self.on_death
        del self.on_death
        del self.is_visible
        if callable(_on_death):
            _on_death()

    def on_expired(self):
        """Callback for notification expiry"""
        # Update position
        target = [self.initial_position[0] + 0.2, self.initial_position[1]]

        self.move_to(target, self.fade_time, note_position=False)
        self.fade(self.fade_time, out=True)

        death_timer = Timer(end=self.fade_time, disposable=True)
        death_timer.on_target = self.on_cleanup

    def update(self, delta_time):
        """Update all active timers
        Handle visibility transitions

        :param delta_time: time since last update
        """
        if callable(self.is_visible):
            _visible = self.visible
            self.visible = self.is_visible()
            became_visible = self.visible and not self._visible
            if became_visible:
                self.fade(self.fade_time, out=False)


class UIPanel(Panel):

    def __init__(self, system):
        super().__init__(system, "UIPanel")

        self._notifications = []
        self._free_slot = []

        self._notification_size = [1.0, 0.06]

        self.start_position = [1 - self._notification_size[0],
                               1 - self._notification_size[1]]
        self.entry_padding = 0.02
        self.panel_padding = 0.01

        # Main UI
        self.dark_grey = [0.1, 0.1, 0.1, 1]
        self.light_grey = [0.3, 0.3, 0.3, 1]
        self.faded_grey = [0.3, 0.3, 0.3, 0.3]
        self.faded_white = [1, 1, 1, 0.6]
        self.concern_colour = [1, 0.05, 0.05, 1]
        self.font_size = 32

        main_size = [0.2, 0.8]
        main_pos = [1 - main_size[0] - self.panel_padding, 1 - self.panel_padding - main_size[1]]

        self.notifications_frame = Frame(parent=self, name="NotificationsPanel", size=main_size[:], pos=main_pos[:])
        self.notifications_frame.colors = [self.faded_grey] * 4

        # Framerate graph
        self.graph = Graph(self, "GRAPH", size=[0.1, 0.1], options=CENTERED, resolution=0.3, scale=60)
        self.graph_scale = Label(self.graph, "GraphLabel", text="", pos=[-0.1, 0.85], pt_size=20)
        self.graph_base = Label(self.graph, "GraphBase", text="0", pos=[-0.07, 0.00], pt_size=20)

        # Graph update callback
        callback_framerate = FrameRateDecorator(self.graph.plot)
        self.plot_framerate = DeltaTimeDecorator(callback_framerate)

        self.weapons_box = Frame(self, "weapons", size=[main_size[0], 0.25], pos=[main_pos[0], 0.025])

        self.icon_box = Frame(self.weapons_box, "icons", size=[1.0, 0.5], pos=[0.0, 0.5])
        self.stats_box = Frame(self.weapons_box, "stats", size=[1.0, 0.5], pos=[0.0, 0.0])

        self.weapon_icon = Image(self.icon_box, "icon", "", size=[0.1, 1.0], aspect=314 / 143, pos=[0.0, 0.0],
                                 options=CENTERED)

        bar_size = [1.0, 0.35]
        bar_margin = 0.025
        bar_pos = [max(1 - bar_size[0] - bar_margin, 0),  0.25]

        self.icon_bar = Frame(self.icon_box, "icon_bar", size=bar_size[:], pos=bar_pos[:])
        self.icon_shadow = Image(self.icon_bar, "icon_shadow", "ui/checkers_border.tga", size=[1.6, 1.6], aspect=1.0,
                                 pos=[0.8, 0], options=CENTERY)
        self.icon_back = Frame(self.icon_shadow, "icon_back", size=[0.8, 0.8], aspect=1.0, options=CENTERED)
        self.icon_middle = Frame(self.icon_back, "icon_middle", size=[0.9, 0.9], aspect=1.0, pos=[0.0, 0],
                                 options=CENTERED)
        self.icon_theme = Frame(self.icon_middle, "icon_theme", size=[1.0, 1.0], aspect=1.0, pos=[0.0, 0],
                                options=CENTERED)
        self.icon_checkers = Image(self.icon_middle, "icon_checkers", "ui/checkers_overlay.tga", size=[1.0, 1.0],
                                   aspect=1.0,  pos=[0.0, 0.0], options=CENTERED)

        self.weapon_name = Label(self.icon_bar,  name="weapon_name", text="The Spitter", pt_size=self.font_size,
                                 shadow=True, shadow_color=self.light_grey, options=CENTERY, pos=[0.05, 0.0],
                                 color=self.dark_grey)

        self.rounds_info = Frame(self.stats_box, "clips_info", pos=[0.0, 0.7], size=[0.6, 0.35])
        self.clips_info = Frame(self.stats_box, "rounds_info", pos=[0.0, 0.2], size=[0.6, 0.35])
        self.grenades_info = Frame(self.stats_box, "grenades_info", pos=[0.6, 0.2], size=[0.35, 0.85])

        self.frag_img = Image(self.grenades_info, "frag_img", "ui/frag.tga", pos=[0.0, 0.0], size=[1, 0.9],
                              aspect=41 / 92, options=CENTERY)
        self.flashbang_img = Image(self.grenades_info, "flashbang_img", "ui/flashbang.tga", pos=[0.5, 0.0],
                                   size=[1, 0.9], aspect=41 / 92, options=CENTERY)

        self.frag_info = Frame(self.frag_img, "frag_info", size=[0.6, 0.35], aspect=1, pos=[0.0, 0.0], options=CENTERED)
        self.frag_box = Frame(self.frag_info, "frag_box", size=[1, 1], pos=[0.0, 0.0], options=CENTERED)

        self.frag_label = Label(self.frag_box, "frag_label", "4", pt_size=self.font_size, options=CENTERED,
                                pos=[0.05, 0.0], color=self.dark_grey)

        self.flashbang_info = Frame(self.flashbang_img, "flashbang_info", size=[0.6, 0.35], aspect=1, options=CENTERED)

        self.flashbang_box = Frame(self.flashbang_info, "flashbang_box", size=[1, 1], pos=[0.0, 0.0], options=CENTERED)

        self.flashbang_label = Label(self.flashbang_box, "flashbang_label", "4", pt_size=self.font_size,
                                     options=CENTERED, pos=[0.05, 0.0], color=self.dark_grey)

        self.rounds_img = Image(self.rounds_info, "rounds_img", "ui/info_box.tga", pos=[0.0, 0.0], size=[1, 1],
                                aspect=1.0, options=CENTERY)
        self.clips_img = Image(self.clips_info, "clips_img", "ui/info_box.tga", pos=[0.0, 0.0], size=[1, 1], aspect=1.0,
                               options=CENTERY)

        self.rounds_box = Frame(self.rounds_info, "rounds_box", size=[0.6, 1.0], pos=[0.3, 0.0], options=CENTERY)
        self.clips_box = Frame(self.clips_info, "clips_box", size=[0.6, 1.0], pos=[0.3, 0.0], options=CENTERY)

        self.rounds_label = Label(self.rounds_box, name="rounds_label", text="ROUNDS", pt_size=self.font_size,
                                  options=CENTERY, pos=[0.05, 0.0], color=self.dark_grey)

        self.clips_label = Label(self.clips_box, name="clips_label", text="CLIPS", pt_size=self.font_size,
                                 options=CENTERY, pos=[0.05, 0.0], color=self.dark_grey)

        self.rounds_value = Label(self.rounds_img, name="rounds_value", text="100", pt_size=self.font_size,
                                  options=CENTERED, pos=[0.05, 0.0], color=self.dark_grey)

        self.clips_value = Label(self.clips_img, name="clips_value", text="4", pt_size=self.font_size, options=CENTERED,
                                 pos=[0.05, 0.0], color=self.dark_grey)

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

        self.entries = {"ammo": (self.rounds_info, self.rounds_value), "clips": (self.clips_info, self.clips_value),
                        "frags": (self.frag_box, self.frag_label), "flashbangs": (self.flashbang_box,
                                                                                  self.flashbang_label)}
        self.handled_concerns = {}

        self.health_indicator = Image(self, "health", "ui/health_overlay.tga", size=[1.0, 1.0], pos=[0.0, 0.0],
                                      options=CENTERED)
        self.health_indicator.color[-1] = 0.0

    def _create_concern_animation(self, widget):
        """Creates a colour changing animation for a BGUI widget

        :param widget: BGUI widget
        """
        def _update_colour():
            """Interpolate the alpha channel of a widgets colour
            Set other channels to error colour
            """
            colour = self.concern_colour.copy()
            colour[-1] = 1 - timer.progress
            widget.colors = [colour] * 4

        timer = Timer(1.0, repeat=True, disposable=True)
        timer.on_update = _update_colour

        return timer

    @property
    def icon_colour(self):
        return self.icon_theme.colors[0]

    @icon_colour.setter
    def icon_colour(self, value):
        self.icon_theme.colors = create_gradient(value, 1 / 3)

    @ReceiveMessage.global_listener
    def create_notification(self, message, *args, **kwargs):
        """Creates and adds a Notification instance to the UI

        :param message: message to display
        :param *args: additional arguments
        :param **kwargs: additional keyword arguments
        :returns: Notification instance
        """

        if self._notifications:
            position = self._notifications[-1].initial_position
            position = [position[0], position[1] - self._notifications[-1].initial_height[1]]

        else:
            position = self.start_position[:]

        # Apply padding
        position[1] -= self.entry_padding

        notification = Notification(self.notifications_frame, *args, pos=position, message=message,
                                    font_size=self.font_size, size=self._notification_size[:], **kwargs)

        # Catch death event
        notification.on_death = lambda: self.delete_notification(notification)
        notification.is_visible = lambda: bool(notification.position[1] > self.notifications_frame.position[1])
        notification.visible = False

        self._notifications.append(notification)
        return notification

    def delete_notification(self, notification):
        """Removes notification from the UI

        :param notification: Notification instance
        """
        self._notifications.remove(notification)
        self.notifications_frame._remove_widget(notification)

    @TeamSelectionUpdatedSignal.global_listener
    def enable(self, target):
        """Callback for team selection
        Sets panel visible
        """
        self.visible = True

    @staticmethod
    def is_concerning(name, field, label):
        """Test for UI entry concern status

        :param name: name of entry
        :param field: drawn field of entry
        :param label: text label of entry
        :returns: result boolean
        """
        if label.text == "0":
            return True

    @UIHealthChangedSignal.global_listener
    def on_health_changed(self, health, full_health=100):
        """Callback for health change

        :param health: health value
        :param full_health: full health value (optional)
        """
        health_fraction = health / full_health
        self.health_indicator.color[-1] = 1 - health_fraction

    @UIWeaponChangedSignal.global_listener
    def on_weapon_changed(self, weapon):
        """Callback for weapon change

        :param weapon: weapon instance
        """
        weapon_name = weapon.__class__.__name__
        icon_relative_path = weapon.resources["icon"][weapon.icon_path]
        icon_path = ResourceManager.from_relative_path(icon_relative_path)

        # Set name of new weapon
        self.weapon_name.text = weapon_name

        # Set icon of new weapon
        self.weapon_icon.update_image(icon_path)

        # Set colour of checker board background
        self.icon_colour = weapon.theme_colour

    def raise_concern(self, name, field, label):
        """Callback for UI entry which invokes a concern

        :param name: name of entry
        :param field: drawn field of entry
        :param label: text label of entry
        """
        self.create_notification("Ran out of {}!".format(name), alive_time=10)

    def update(self, delta_time):
        """Update game user interface

        :param delta_time: time since last update
        """
        # Update a copy, so that we don't mutate whilst iterating
        for notification in self._notifications[:]:
            notification.update(delta_time)

        # Update positions due to deletion/addition
        self.update_positions()

        # Update any animation for alertable resources
        self.update_concerns()

        self.plot_framerate()
        self.graph.scale = WorldInfo.tick_rate
        self.graph_scale.text = str(self.graph.scale)

        super().update(delta_time)

    def update_concerns(self):
        """Considers all registered entries for concerns"""
        # Create any alert timers
        create_concern = self._create_concern_animation
        concerns = self.handled_concerns
        is_concerning = self.is_concerning
        raise_concern = self.raise_concern

        for name, (field, label) in self.entries.items():
            if name in concerns or not is_concerning(name, field, label):
                continue

            raise_concern(name, field, label)
            concerns[name] = create_concern(field)

        # Check for handled timers
        handled = []
        for name, timer in concerns.items():
            field, label = self.entries[name]

            # Concern is no longer valid
            if not is_concerning(name, field, label):
                timer.stop()
                handled.append(name)

        # Remove handled UI timers
        for handled_name in handled:
            concerns.pop(handled_name)

    @UIWeaponDataChangedSignal.global_listener
    def update_entry(self, name, value):
        """Update value of a registered entry

        :param name: name of registered entry
        :param value: new value for entry
        """
        value_field = self.entries[name][1]
        value_field.text = str(value)

    def update_positions(self):
        """Update notification positions to account for individual changes"""
        # Handle sliding up when deleting notifications_frame
        x_offset, y_offset = self.start_position

        for index, notification in enumerate(self._notifications):
            y_step = self.entry_padding + self._notification_size[1]

            calculated_y = y_offset - (index * y_step)
            position_y = notification.initial_position[1]

            if position_y == calculated_y:
                continue

            new_position = [x_offset, calculated_y]
            notification.move_to(new_position)


class BGESystem(System):

    def __init__(self):
        super().__init__()

        self.choose_team = TeamPanel(self)
        self.connect_panel = ConnectPanel(self)
        self.ui_panel = UIPanel(self)

    @ConnectionSuccessSignal.global_listener
    def invoke(self, target):
        ReceiveMessage.invoke("Connected to {}".format(target.instance_id), alive_time=-1, scroll_time=4)
